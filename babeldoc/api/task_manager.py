"""
任务管理系统
管理翻译任务的生命周期，包括创建、执行、监控和结果管理
"""
import asyncio
import logging
import threading
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
import json
import tempfile

from babeldoc.api.models import TaskStatus, TaskInfo, TranslationRequest, OutputFileInfo
from babeldoc.api.cache import get_cache, FileCache
from babeldoc.format.pdf.translation_config import TranslationConfig, WatermarkOutputMode
from babeldoc.translator.translator import OpenAITranslator, set_translate_rate_limiter
from babeldoc.glossary import Glossary

logger = logging.getLogger(__name__)


class TaskProgressCallback:
    """任务进度回调"""
    
    def __init__(self, task_id: str, task_manager: 'TaskManager'):
        self.task_id = task_id
        self.task_manager = task_manager
        self.last_progress = 0.0
        self.last_message = ""

    def __call__(self, progress: float, message: str = "", stage: str = ""):
        """更新任务进度"""
        try:
            self.last_progress = progress
            self.last_message = message
            
            self.task_manager.update_task_progress(
                self.task_id, 
                progress, 
                message, 
                stage
            )
        except Exception as e:
            logger.error(f"更新任务进度失败 {self.task_id}: {e}")


class TaskManager:
    """任务管理器 - 使用 CLI 相同的并行处理优化"""
    
    def __init__(self, max_concurrent_tasks: int = 3):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.tasks: Dict[str, TaskInfo] = {}
        self.task_locks: Dict[str, threading.RLock] = {}
        self.progress_callbacks: Dict[str, List[Callable]] = {}
        
        # 🚀 优化：使用优先级线程池执行器，与CLI保持一致
        from babeldoc.utils.priority_thread_pool_executor import PriorityThreadPoolExecutor
        self.processing_tasks = set()
        self.translation_executor = PriorityThreadPoolExecutor(
            max_workers=max_concurrent_tasks * 2,  # 允许更多并行度
            thread_name_prefix="BabelDoc-Translation"
        )
        
        # 缓存管理
        self.file_cache: FileCache = get_cache('uploaded_files', max_age_days=7)
        self.result_cache: FileCache = get_cache('translation_results', max_age_days=30)
        
        # 任务持久化
        self.task_data_file = Path(tempfile.gettempdir()) / "babeldoc_tasks.json"
        
        # 任务结果目录
        self.results_base_dir = Path(tempfile.gettempdir()) / "babeldoc_results"
        self.results_base_dir.mkdir(parents=True, exist_ok=True)
        
        # 锁
        self._lock = threading.RLock()
        
        # 加载已有任务
        self._load_tasks()
        
        # 启动清理线程
        self._start_cleanup_thread()
        
        logger.info(f"任务管理器初始化完成，最大并发任务数: {max_concurrent_tasks}")

    def __del__(self):
        """清理资源"""
        try:
            if hasattr(self, 'translation_executor'):
                self.translation_executor.shutdown(wait=True)
        except Exception as e:
            logger.error(f"清理任务管理器资源失败: {e}")

    def _load_tasks(self):
        """加载持久化的任务数据"""
        try:
            if self.task_data_file.exists():
                with open(self.task_data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for task_data in data.get('tasks', []):
                        try:
                            # 数据迁移：处理老格式的 output_files
                            if 'output_files' in task_data and isinstance(task_data['output_files'], list):
                                # 检查是否是老格式（字符串列表）
                                if task_data['output_files'] and isinstance(task_data['output_files'][0], str):
                                    # 转换为新格式
                                    old_output_files = task_data['output_files']
                                    task_data['output_file_paths'] = old_output_files.copy()  # 向后兼容
                                    task_data['output_files'] = []
                                    
                                    # 尝试从文件路径推断结构化信息
                                    for file_path in old_output_files:
                                        try:
                                            if Path(file_path).exists():
                                                file_info = OutputFileInfo.from_file_path(file_path)
                                                task_data['output_files'].append(file_info.model_dump())
                                        except Exception as e:
                                            logger.warning(f"迁移输出文件数据失败 {file_path}: {e}")
                            
                            # 确保向后兼容字段存在
                            if 'output_file_paths' not in task_data:
                                task_data['output_file_paths'] = []
                            
                            # 将字典转换为 TaskInfo 对象
                            task_info = TaskInfo(**task_data)
                            
                            # 重置处理中的任务状态
                            if task_info.status == TaskStatus.PROCESSING:
                                task_info.status = TaskStatus.FAILED
                                task_info.error_message = "服务重启，任务中断"
                                task_info.updated_at = datetime.now()
                            
                            self.tasks[task_info.task_id] = task_info
                            self.task_locks[task_info.task_id] = threading.RLock()
                            
                        except Exception as e:
                            logger.error(f"加载任务数据失败: {e}")
                            
                logger.info(f"加载了 {len(self.tasks)} 个历史任务")
        except Exception as e:
            logger.error(f"加载任务持久化数据失败: {e}")

    def _save_tasks(self):
        """保存任务数据到文件"""
        try:
            # 转换为可序列化的格式
            serializable_tasks = []
            for task in self.tasks.values():
                task_dict = task.model_dump()
                # 转换 datetime 对象
                for key in ['created_at', 'updated_at']:
                    if key in task_dict and isinstance(task_dict[key], datetime):
                        task_dict[key] = task_dict[key].isoformat()
                serializable_tasks.append(task_dict)
            
            data = {
                'tasks': serializable_tasks,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.task_data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"保存任务数据失败: {e}")

    def _start_cleanup_thread(self):
        """启动任务清理线程"""
        def cleanup_worker():
            while True:
                try:
                    self._cleanup_old_tasks()
                    threading.Event().wait(3600)  # 每小时清理一次
                except Exception as e:
                    logger.error(f"任务清理线程出错: {e}")
                    threading.Event().wait(300)  # 出错时5分钟后重试
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.info("启动任务清理线程")

    def _cleanup_old_tasks(self):
        """清理过期任务和结果文件"""
        with self._lock:
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(days=7)  # 保留7天的任务记录
            
            to_remove = []
            for task_id, task in self.tasks.items():
                if task.updated_at < cutoff_time and task.status in [
                    TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED
                ]:
                    to_remove.append(task_id)
            
            for task_id in to_remove:
                # 清理结果文件
                try:
                    result_dir = self.results_base_dir / task_id
                    if result_dir.exists():
                        import shutil
                        shutil.rmtree(result_dir, ignore_errors=True)
                        logger.info(f"清理任务 {task_id} 的结果文件目录: {result_dir}")
                except Exception as e:
                    logger.warning(f"清理任务 {task_id} 结果文件失败: {e}")
                
                # 清理任务记录
                del self.tasks[task_id]
                if task_id in self.task_locks:
                    del self.task_locks[task_id]
                if task_id in self.progress_callbacks:
                    del self.progress_callbacks[task_id]
            
            if to_remove:
                logger.info(f"清理了 {len(to_remove)} 个过期任务")
                self._save_tasks()

    def create_task(
        self, 
        request: TranslationRequest, 
        input_file_path: Path,
        input_filename: str
    ) -> str:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        
        with self._lock:
            # 创建任务信息
            task_info = TaskInfo(
                task_id=task_id,
                status=TaskStatus.PENDING,
                progress=0.0,
                message="任务已创建，等待处理",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                input_filename=input_filename,
                input_file_size=input_file_path.stat().st_size,
                lang_in=request.lang_in,
                lang_out=request.lang_out,
                pages=request.pages,
                output_files=[]
            )
            
            self.tasks[task_id] = task_info
            self.task_locks[task_id] = threading.RLock()
            self.progress_callbacks[task_id] = []
            
            # 保存任务数据
            self._save_tasks()
            
            logger.info(f"创建翻译任务: {task_id}")
            return task_id

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        return self.tasks.get(task_id)

    def list_tasks(self, page: int = 1, page_size: int = 20) -> tuple[List[TaskInfo], int]:
        """列出任务"""
        with self._lock:
            # 按创建时间倒序排列
            sorted_tasks = sorted(
                self.tasks.values(), 
                key=lambda x: x.created_at, 
                reverse=True
            )
            
            total = len(sorted_tasks)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            
            page_tasks = sorted_tasks[start_idx:end_idx]
            return page_tasks, total

    def update_task_progress(
        self, 
        task_id: str, 
        progress: float, 
        message: str = "",
        stage: str = ""
    ):
        """更新任务进度"""
        if task_id not in self.tasks:
            return
        
        with self.task_locks.get(task_id, threading.RLock()):
            task = self.tasks[task_id]
            task.progress = max(0, min(100, progress))
            if message:
                task.message = message
            task.updated_at = datetime.now()
            
            # 通知进度回调
            for callback in self.progress_callbacks.get(task_id, []):
                try:
                    callback(progress, message, stage)
                except Exception as e:
                    logger.error(f"进度回调失败: {e}")
            
            # 保存任务数据
            self._save_tasks()

    def update_task_status(
        self, 
        task_id: str, 
        status: TaskStatus, 
        message: str = "",
        error_message: Optional[str] = None,
        error_traceback: Optional[str] = None
    ):
        """更新任务状态"""
        if task_id not in self.tasks:
            return
        
        with self.task_locks.get(task_id, threading.RLock()):
            task = self.tasks[task_id]
            task.status = status
            if message:
                task.message = message
            if error_message:
                task.error_message = error_message
            if error_traceback:
                task.error_traceback = error_traceback
            task.updated_at = datetime.now()
            
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                self.processing_tasks.discard(task_id)
            
            # 保存任务数据
            self._save_tasks()

    def add_output_file(self, task_id: str, file_path: str):
        """添加输出文件"""
        if task_id not in self.tasks:
            return
        
        with self.task_locks.get(task_id, threading.RLock()):
            task = self.tasks[task_id]
            
            # 创建结构化文件信息
            try:
                file_info = OutputFileInfo.from_file_path(file_path)
                
                # 检查是否已存在相同文件
                if not any(existing.file_path == file_path for existing in task.output_files):
                    task.output_files.append(file_info)
                    
                    # 向后兼容：同时更新字符串列表
                    if file_path not in task.output_file_paths:
                        task.output_file_paths.append(file_path)
                    
                    logger.info(f"添加输出文件: {file_path}, 类型: {file_info.file_type.value}")
                
            except Exception as e:
                logger.error(f"添加输出文件失败 {file_path}: {e}")
                # 兜底：至少保证字符串列表中有记录
                if file_path not in task.output_file_paths:
                    task.output_file_paths.append(file_path)
            
            task.updated_at = datetime.now()
            
            # 保存任务数据
            self._save_tasks()

    def register_progress_callback(self, task_id: str, callback: Callable):
        """注册进度回调"""
        if task_id not in self.progress_callbacks:
            self.progress_callbacks[task_id] = []
        self.progress_callbacks[task_id].append(callback)

    def can_start_task(self) -> bool:
        """检查是否可以启动新任务"""
        return len(self.processing_tasks) < self.max_concurrent_tasks

    async def execute_task(self, task_id: str, request: TranslationRequest, input_file_path: Path):
        """执行翻译任务 - 优化版，使用优先级调度"""
        if not self.can_start_task():
            logger.warning(f"达到最大并发任务数限制，任务 {task_id} 需要等待")
            # TODO: 可以实现队列机制
            return
        
        self.processing_tasks.add(task_id)
        self.update_task_status(task_id, TaskStatus.PROCESSING, "开始处理翻译任务")
        
        # 计算任务优先级（基于文件大小和QPS设置）
        file_size = input_file_path.stat().st_size
        priority = max(1000000 - file_size // 1024, 1)  # 越小文件优先级越高
        
        try:
            # 🚀 关键优化：使用优先级线程池执行翻译任务
            future = self.translation_executor.submit(
                self._execute_task_sync,
                task_id, request, input_file_path,
                priority=priority
            )
            
            # 等待任务完成
            await asyncio.get_event_loop().run_in_executor(None, future.result)
            
            logger.info(f"任务 {task_id} 执行成功")
            
        except Exception as e:
            error_msg = f"翻译任务执行失败: {str(e)}"
            error_traceback = traceback.format_exc()
            
            self.update_task_status(
                task_id, 
                TaskStatus.FAILED, 
                error_msg,
                error_msg,
                error_traceback
            )
            
            logger.error(f"任务 {task_id} 执行失败: {e}", exc_info=True)
            
        finally:
            self.processing_tasks.discard(task_id)

    def _execute_task_sync(self, task_id: str, request: TranslationRequest, input_file_path: Path):
        """同步执行翻译任务（在线程池中调用）- 优化版本，改进事件循环管理"""
        import asyncio
        import threading
        
        # 获取或创建当前线程的事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # 当前线程没有事件循环，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            # 创建进度回调
            progress_callback = TaskProgressCallback(task_id, self)
            
            # 执行异步翻译
            result_files = loop.run_until_complete(
                self._do_translation(task_id, request, input_file_path, progress_callback)
            )
            
            # 记录结果文件（直接使用持久化路径，不依赖缓存）
            for result_file in result_files:
                if result_file.exists():
                    # 直接记录持久化文件路径
                    self.add_output_file(task_id, str(result_file))
                    logger.info(f"记录结果文件: {result_file}")
            
            self.update_task_status(
                task_id, 
                TaskStatus.COMPLETED, 
                f"翻译完成，生成了 {len(result_files)} 个文件"
            )
            self.update_task_progress(task_id, 100.0, "翻译完成")
            
        except asyncio.CancelledError:
            logger.info(f"任务 {task_id} 被取消")
            self.update_task_status(task_id, TaskStatus.CANCELLED, "任务被取消")
            
        except Exception as e:
            error_msg = f"翻译任务执行失败: {str(e)}"
            error_traceback = traceback.format_exc()
            
            self.update_task_status(
                task_id, 
                TaskStatus.FAILED, 
                error_msg,
                error_msg,
                error_traceback
            )
            logger.error(f"任务 {task_id} 执行失败: {e}", exc_info=True)
            
        finally:
            # 正确清理事件循环
            try:
                # 取消所有未完成的任务
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        task.cancel()
                    
                    # 等待任务取消完成
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                # 安全关闭事件循环
                loop.close()
                
            except Exception as cleanup_error:
                logger.warning(f"清理事件循环时出错: {cleanup_error}")
                # 强制关闭
                try:
                    if not loop.is_closed():
                        loop.close()
                except Exception:
                    pass

    async def _do_translation(
        self, 
        task_id: str, 
        request: TranslationRequest, 
        input_file_path: Path,
        progress_callback: TaskProgressCallback
    ) -> List[Path]:
        """执行具体的翻译操作，使用 CLI 相同的优化技术"""
        
        progress_callback(5.0, "初始化翻译器")
        
        # 初始化翻译器（使用与CLI相同的配置）
        translator = OpenAITranslator(
            lang_in=request.lang_in,
            lang_out=request.lang_out,
            model=request.openai_model,
            base_url=request.openai_base_url,
            api_key=request.openai_api_key,
            ignore_cache=request.ignore_cache
        )
        
        # 设置速率限制（与CLI保持一致）
        set_translate_rate_limiter(request.qps)
        
        progress_callback(10.0, "加载文档布局模型")
        
        # 初始化文档布局模型
        from babeldoc.docvision.doclayout import DocLayoutModel
        doc_layout_model = DocLayoutModel.load_onnx()
        
        # 表格模型
        table_model = None
        if request.translate_table_text:
            from babeldoc.docvision.table_detection.rapidocr import RapidOCRModel
            table_model = RapidOCRModel()
        
        progress_callback(15.0, "创建翻译配置")
        
        # 转换水印模式
        watermark_mode = WatermarkOutputMode.Watermarked
        if request.watermark_output_mode.value == "no_watermark":
            watermark_mode = WatermarkOutputMode.NoWatermark
        elif request.watermark_output_mode.value == "both":
            watermark_mode = WatermarkOutputMode.Both
        
        # 创建单独的临时工作目录，避免文件冲突
        import tempfile
        import uuid
        temp_base_dir = Path(tempfile.gettempdir()) / f"babeldoc_api_{uuid.uuid4().hex[:8]}"
        temp_base_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 创建翻译配置（使用与CLI完全相同的参数）
            config = TranslationConfig(
                input_file=str(input_file_path),
                translator=translator,
                doc_layout_model=doc_layout_model,
                lang_in=request.lang_in,
                lang_out=request.lang_out,
                pages=request.pages,
                output_dir=temp_base_dir / "output",
                no_dual=request.no_dual,
                no_mono=request.no_mono,
                min_text_length=request.min_text_length,
                watermark_output_mode=watermark_mode,
                qps=request.qps,
                formular_font_pattern=request.formular_font_pattern,
                formular_char_pattern=request.formular_char_pattern,
                split_short_lines=request.split_short_lines,
                short_line_split_factor=request.short_line_split_factor,
                skip_clean=request.skip_clean,
                dual_translate_first=request.dual_translate_first,
                disable_rich_text_translate=request.disable_rich_text_translate,
                enhance_compatibility=request.enhance_compatibility,
                use_alternating_pages_dual=request.use_alternating_pages_dual,
                table_model=table_model,
                show_char_box=request.show_char_box,
                skip_scanned_detection=request.skip_scanned_detection,
                ocr_workaround=request.ocr_workaround,
                custom_system_prompt=request.custom_system_prompt,
                working_dir=temp_base_dir / "work",
                skip_formula_offset_calculation=request.skip_formula_offset_calculation,
                figure_table_protection_threshold=request.figure_table_protection_threshold,
                remove_non_formula_lines=request.remove_non_formula_lines,
                enable_graphic_element_process=request.enable_graphic_element_process,
                # 关键优化：设置并行工作线程数
                pool_max_workers=max(request.qps, 2),  # 至少2个线程，或等于QPS值
                # 进度报告间隔
                report_interval=0.1,  # 100ms 更新一次进度
            )
            
            progress_callback(20.0, "开始异步PDF翻译")
            
            # 🚀 关键优化：使用CLI相同的异步翻译接口
            from babeldoc.format.pdf.high_level import async_translate
            
            result_files = []
            
            try:
                # 异步翻译，实时获取进度
                async for event in async_translate(config):
                    if event["type"] == "progress_update":
                        # 将翻译进度映射到 20-95% 范围
                        mapped_progress = 20.0 + (event["overall_progress"] * 0.75)
                        # 安全获取消息，避免 KeyError
                        stage = event.get('stage', '翻译中')
                        message = event.get('message', '')
                        progress_callback(
                            mapped_progress, 
                            f"{stage}: {message}" if message else stage
                        )
                    
                    elif event["type"] == "finish":
                        progress_callback(95.0, "翻译完成，收集结果文件")
                        
                        # 获取翻译结果
                        translate_result = event["translate_result"]
                        logger.info(f"翻译完成，结果: {translate_result}")
                        
                        # 收集输出文件到持久化目录
                        for file_path in (temp_base_dir / "output").rglob("*.pdf"):
                            if file_path.is_file():
                                # 创建持久化结果目录
                                result_dir = self.results_base_dir / task_id
                                result_dir.mkdir(parents=True, exist_ok=True)
                                
                                # 复制到持久化目录，保持原有文件名结构
                                result_file = result_dir / file_path.name
                                import shutil
                                shutil.copy2(file_path, result_file)
                                result_files.append(result_file)
                                logger.info(f"收集结果文件到持久化目录: {result_file}")
                        
                        break
                    
                    elif event["type"] == "error":
                        error_msg = f"翻译过程中出现错误: {event.get('error', '未知错误')}"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                        
            except asyncio.CancelledError:
                logger.info(f"任务 {task_id} 被取消")
                raise
                
            except Exception as e:
                logger.error(f"异步翻译失败: {e}", exc_info=True)
                raise
            
            progress_callback(100.0, f"翻译完成，生成了 {len(result_files)} 个文件")
            
            return result_files
            
        finally:
            # 延迟清理临时目录，避免文件访问冲突
            try:
                import time
                time.sleep(0.5)  # 等待文件句柄释放
                if temp_base_dir.exists():
                    import shutil
                    shutil.rmtree(temp_base_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"清理临时目录失败，将在后台清理: {e}")
                # 异步清理，避免阻塞主流程
                import threading
                import time
                import shutil
                def cleanup_later():
                    try:
                        time.sleep(2.0)
                        if temp_base_dir.exists():
                            shutil.rmtree(temp_base_dir, ignore_errors=True)
                    except Exception:
                        pass  # 忽略清理错误
                threading.Thread(target=cleanup_later, daemon=True).start()

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task.status == TaskStatus.PROCESSING:
            # 实际的取消逻辑需要更复杂的实现
            # 这里只是简单标记为取消状态
            self.update_task_status(task_id, TaskStatus.CANCELLED, "任务已取消")
            return True
        
        return False

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        with self._lock:
            if task_id not in self.tasks:
                return False
            
            # 清理输出文件缓存
            task = self.tasks[task_id]
            
            # 清理结构化文件信息中的文件
            for file_info in task.output_files:
                try:
                    Path(file_info.file_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.error(f"删除输出文件失败: {e}")
            
            # 清理向后兼容的文件路径列表
            for output_file_path in task.output_file_paths:
                try:
                    Path(output_file_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.error(f"删除输出文件失败: {e}")
            
            # 删除任务记录
            del self.tasks[task_id]
            if task_id in self.task_locks:
                del self.task_locks[task_id]
            if task_id in self.progress_callbacks:
                del self.progress_callbacks[task_id]
            self.processing_tasks.discard(task_id)
            
            # 保存任务数据
            self._save_tasks()
            
            logger.info(f"删除任务: {task_id}")
            return True


# 全局任务管理器实例
_task_manager: Optional[TaskManager] = None
_task_manager_lock = threading.Lock()


def get_task_manager() -> TaskManager:
    """获取全局任务管理器实例"""
    global _task_manager
    with _task_manager_lock:
        if _task_manager is None:
            _task_manager = TaskManager()
        return _task_manager