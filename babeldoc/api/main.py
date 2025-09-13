"""
FastAPI 服务主应用
提供PDF翻译的HTTP API服务
"""
import sys
import asyncio
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
import mimetypes
import psutil

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Query, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager

from babeldoc.api.models import (
    TranslationRequest, TranslationResponse, TaskInfo, TaskStatus,
    TaskListResponse, FileUploadResponse, CacheStats, HealthResponse,
    ErrorResponse, ConfigResponse, ProgressUpdate, WatermarkMode
)
from babeldoc.api.task_manager import get_task_manager, TaskManager
from babeldoc.api.cache import get_cache, FileCache

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 应用启动时间
app_start_time = time.time()

# 支持的语言列表
SUPPORTED_LANGUAGES = {
    "en": "English",
    "zh": "中文",
    "zh-cn": "简体中文",
    "zh-tw": "繁体中文",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "pt": "葡萄牙语",
    "it": "意大利语",
    "ar": "阿拉伯语",
    "hi": "印地语",
    "th": "泰语",
    "vi": "越南语",
    "nl": "荷兰语",
    "sv": "瑞典语",
    "da": "丹麦语",
    "no": "挪威语",
    "fi": "芬兰语",
    "tr": "土耳其语",
    "pl": "波兰语",
    "cs": "捷克语",
    "hu": "匈牙利语",
    "ro": "罗马尼亚语",
    "bg": "保加利亚语",
    "hr": "克罗地亚语",
    "sk": "斯洛伐克语",
    "sl": "斯洛文尼亚语",
    "et": "爱沙尼亚语",
    "lv": "拉脱维亚语",
    "lt": "立陶宛语",
    "uk": "乌克兰语",
    "be": "白俄罗斯语",
    "mk": "马其顿语",
    "sq": "阿尔巴尼亚语",
    "bs": "波斯尼亚语",
    "me": "黑山语",
    "sr": "塞尔维亚语"
}

# 全局变量
task_manager: TaskManager
file_cache: FileCache
result_cache: FileCache


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global task_manager, file_cache, result_cache
    
    # 启动时初始化
    logger.info("初始化 BabelDOC API 服务")
    task_manager = get_task_manager()
    file_cache = get_cache('uploaded_files', max_age_days=1)  # 上传文件保存1天
    result_cache = get_cache('translation_results', max_age_days=7)  # 翻译结果保存7天
    
    # 确保温身
    try:
        from babeldoc.assets.assets import warmup
        await asyncio.get_event_loop().run_in_executor(None, warmup)
        logger.info("资源预热完成")
    except Exception as e:
        logger.error(f"资源预热失败: {e}")
    
    yield
    
    # 关闭时清理
    logger.info("关闭 BabelDOC API 服务")


# 创建 FastAPI 应用
app = FastAPI(
    title="BabelDOC Translation API",
    description="PDF文档翻译API服务",
    version="0.5.9",
    lifespan=lifespan
)

# 添加中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需要限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


# 异常处理
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """HTTP异常处理"""
    error_response = ErrorResponse(
        error="HTTP_ERROR",
        message=exc.detail,
        timestamp=datetime.now()
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(mode='json')
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """通用异常处理"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    error_response = ErrorResponse(
        error="INTERNAL_ERROR",
        message="服务器内部错误",
        detail=str(exc),
        timestamp=datetime.now()
    )
    return JSONResponse(
        status_code=500,
        content=error_response.model_dump(mode='json')
    )


# 依赖函数
async def validate_api_key(api_key: Optional[str] = None):
    """验证API密钥（可选实现）"""
    # 这里可以实现API密钥验证逻辑
    # 暂时跳过验证
    pass


# API 端点

@app.get("/", response_model=dict)
async def root():
    """根路径"""
    return {
        "service": "BabelDOC Translation API",
        "version": "0.5.9",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    try:
        # 获取系统信息
        system_info = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage("/").percent,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        }
        
        # 获取缓存统计
        cache_stats = CacheStats(**result_cache.get_cache_stats())
        
        uptime = time.time() - app_start_time
        
        return HealthResponse(
            status="healthy",
            version="0.5.9",
            uptime=uptime,
            cache_stats=cache_stats,
            system_info=system_info
        )
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(status_code=500, detail="健康检查失败")


@app.get("/config", response_model=ConfigResponse)
async def get_config():
    """获取配置信息"""
    default_request = TranslationRequest(openai_api_key="YOUR_API_KEY")
    
    return ConfigResponse(
        supported_languages=SUPPORTED_LANGUAGES,
        default_settings=default_request,
        limits={
            "max_file_size_mb": 100,
            "max_concurrent_tasks": 3,
            "supported_formats": ["pdf"],
            "max_pages": 1000
        }
    )


@app.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    api_key: Optional[str] = Depends(validate_api_key)
):
    """上传PDF文件"""
    # 验证文件类型
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="只支持PDF文件")
    
    # 验证文件大小（100MB限制）
    file_content = await file.read()
    if len(file_content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小超过100MB限制")
    
    try:
        # 生成文件ID并缓存文件
        file_id = file_cache.get_cache_key(file_content, {"filename": file.filename})
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_path = Path(tmp_file.name)
        
        # 缓存文件
        cached_path = file_cache.put(
            file_id, 
            tmp_path, 
            {
                "original_filename": file.filename,
                "content_type": file.content_type,
                "uploaded_at": datetime.now().isoformat()
            }
        )
        
        # 清理临时文件
        tmp_path.unlink(missing_ok=True)
        
        return FileUploadResponse(
            file_id=file_id,
            filename=file.filename,
            file_size=len(file_content),
            uploaded_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=1)
        )
        
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@app.post("/translate", response_model=TranslationResponse)
async def translate_document(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    file_id: Optional[str] = Form(None),
    # 翻译参数作为表单字段
    lang_in: str = Form("en"),
    lang_out: str = Form("zh"),
    openai_api_key: str = Form(...),
    openai_model: str = Form("gpt-4o-mini"),
    openai_base_url: Optional[str] = Form(None),
    pages: Optional[str] = Form(None),
    min_text_length: int = Form(5),
    no_dual: bool = Form(False),
    no_mono: bool = Form(False),
    dual_translate_first: bool = Form(False),
    use_alternating_pages_dual: bool = Form(False),
    watermark_output_mode: WatermarkMode = Form(WatermarkMode.WATERMARKED),
    qps: int = Form(4),
    enhance_compatibility: bool = Form(False),
    translate_table_text: bool = Form(False),
    custom_system_prompt: Optional[str] = Form(None),
    api_key: Optional[str] = Depends(validate_api_key)
):
    """翻译PDF文档（支持文件上传）"""
    
    # 构建翻译请求对象
    request = TranslationRequest(
        lang_in=lang_in,
        lang_out=lang_out,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        openai_base_url=openai_base_url,
        pages=pages,
        min_text_length=min_text_length,
        no_dual=no_dual,
        no_mono=no_mono,
        dual_translate_first=dual_translate_first,
        use_alternating_pages_dual=use_alternating_pages_dual,
        watermark_output_mode=watermark_output_mode,
        qps=qps,
        enhance_compatibility=enhance_compatibility,
        translate_table_text=translate_table_text,
        custom_system_prompt=custom_system_prompt
    )
    
    # 获取输入文件
    input_file_path: Optional[Path] = None
    input_filename: str = ""
    
    if file:
        # 直接上传的文件
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="只支持PDF文件")
        
        file_content = await file.read()
        if len(file_content) > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件大小超过100MB限制")
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_file.write(file_content)
            input_file_path = Path(tmp_file.name)
            input_filename = file.filename
            
    elif file_id:
        # 使用已上传的文件
        cached_path = file_cache.get(file_id)
        if not cached_path:
            raise HTTPException(status_code=404, detail="文件不存在或已过期")
        
        input_file_path = cached_path
        # 从缓存元数据获取原文件名
        cache_items = file_cache.list_cache_items()
        for item in cache_items:
            if item['key'] == file_id:
                input_filename = item['metadata'].get('original_filename', 'unknown.pdf')
                break
                
    else:
        raise HTTPException(status_code=400, detail="必须提供file或file_id参数")
    
    try:
        # 检查并发任务限制
        if not task_manager.can_start_task():
            raise HTTPException(status_code=429, detail="服务器繁忙，请稍后重试")
        
        # 创建翻译任务
        task_id = task_manager.create_task(request, input_file_path, input_filename)
        
        # 在后台执行翻译
        background_tasks.add_task(
            task_manager.execute_task, 
            task_id, 
            request, 
            input_file_path
        )
        
        return TranslationResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="翻译任务已创建，正在处理中",
            estimated_time=300  # 预估5分钟
        )
        
    except Exception as e:
        logger.error(f"创建翻译任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建翻译任务失败: {str(e)}")


@app.post("/translate/json", response_model=TranslationResponse)
async def translate_with_json(
    request: TranslationRequest,
    background_tasks: BackgroundTasks,
    file_id: str,
    api_key: Optional[str] = Depends(validate_api_key)
):
    """使用JSON格式翻译文档（需要先上传文件获取file_id）"""
    
    # 使用已上传的文件
    cached_path = file_cache.get(file_id)
    if not cached_path:
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    
    input_file_path = cached_path
    # 从缓存元数据获取原文件名
    input_filename = "unknown.pdf"
    cache_items = file_cache.list_cache_items()
    for item in cache_items:
        if item['key'] == file_id:
            input_filename = item['metadata'].get('original_filename', 'unknown.pdf')
            break
    
    try:
        # 检查并发任务限制
        if not task_manager.can_start_task():
            raise HTTPException(status_code=429, detail="服务器繁忙，请稍后重试")
        
        # 创建翻译任务
        task_id = task_manager.create_task(request, input_file_path, input_filename)
        
        # 在后台执行翻译
        background_tasks.add_task(
            task_manager.execute_task, 
            task_id, 
            request, 
            input_file_path
        )
        
        return TranslationResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="翻译任务已创建，正在处理中",
            estimated_time=300  # 预估5分钟
        )
        
    except Exception as e:
        logger.error(f"创建翻译任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建翻译任务失败: {str(e)}")


@app.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1, description="页号"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    status: Optional[TaskStatus] = Query(None, description="过滤任务状态"),
    api_key: Optional[str] = Depends(validate_api_key)
):
    """列出翻译任务"""
    try:
        tasks, total = task_manager.list_tasks(page, page_size)
        
        # 状态过滤
        if status:
            tasks = [task for task in tasks if task.status == status]
            total = len(tasks)
        
        return TaskListResponse(
            tasks=tasks,
            total=total,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@app.get("/tasks/{task_id}", response_model=TaskInfo)
async def get_task_status(
    task_id: str,
    api_key: Optional[str] = Depends(validate_api_key)
):
    """获取任务状态"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return task


@app.delete("/tasks/{task_id}", response_model=dict)
async def delete_task(
    task_id: str,
    api_key: Optional[str] = Depends(validate_api_key)
):
    """删除任务"""
    if task_manager.delete_task(task_id):
        return {"message": "任务已删除"}
    else:
        raise HTTPException(status_code=404, detail="任务不存在")


@app.post("/tasks/{task_id}/cancel", response_model=dict)
async def cancel_task(
    task_id: str,
    api_key: Optional[str] = Depends(validate_api_key)
):
    """取消任务"""
    if task_manager.cancel_task(task_id):
        return {"message": "任务已取消"}
    else:
        raise HTTPException(status_code=404, detail="任务不存在或无法取消")


@app.get("/tasks/{task_id}/download")
async def download_results(
    task_id: str,
    file_index: int = Query(0, ge=0, description="文件索引"),
    api_key: Optional[str] = Depends(validate_api_key)
):
    """下载翻译结果"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    if file_index >= len(task.output_files):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_path = Path(task.output_files[file_index])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 设置文件名
    filename = f"{task.input_filename}_{task.lang_out}_{file_index}.pdf"
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/pdf'
    )


@app.get("/cache/stats", response_model=CacheStats)
async def get_cache_stats(api_key: Optional[str] = Depends(validate_api_key)):
    """获取缓存统计"""
    return CacheStats(**result_cache.get_cache_stats())


@app.delete("/cache/clear", response_model=dict)
async def clear_cache(api_key: Optional[str] = Depends(validate_api_key)):
    """清空缓存"""
    try:
        file_cache.clear_all()
        result_cache.clear_all()
        return {"message": "缓存已清空"}
    except Exception as e:
        logger.error(f"清空缓存失败: {e}")
        raise HTTPException(status_code=500, detail="清空缓存失败")


# WebSocket 支持（可选）
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/{task_id}")
async def websocket_progress(websocket: WebSocket, task_id: str):
    """WebSocket 实时进度推送"""
    await websocket.accept()
    
    try:
        # 检查任务是否存在
        task = task_manager.get_task(task_id)
        if not task:
            await websocket.send_json({"error": "任务不存在"})
            return
        
        # 注册进度回调
        async def progress_callback(progress: float, message: str, stage: str):
            try:
                update = ProgressUpdate(
                    task_id=task_id,
                    progress=progress,
                    message=message,
                    stage=stage
                )
                await websocket.send_json(update.model_dump())
            except Exception as e:
                logger.error(f"WebSocket 发送失败: {e}")
        
        task_manager.register_progress_callback(task_id, progress_callback)
        
        # 发送当前状态
        current_task = task_manager.get_task(task_id)
        if current_task:
            await websocket.send_json({
                "task_id": task_id,
                "progress": current_task.progress,
                "message": current_task.message,
                "stage": "current",
                "status": current_task.status.value
            })
        
        # 保持连接
        while True:
            # 检查任务状态
            current_task = task_manager.get_task(task_id)
            if current_task and current_task.status in [
                TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED
            ]:
                await websocket.send_json({
                    "task_id": task_id,
                    "progress": current_task.progress,
                    "message": current_task.message,
                    "stage": "final",
                    "status": current_task.status.value
                })
                break
            
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket 连接断开: {task_id}")
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        await websocket.send_json({"error": str(e)})


def main():
    """启动API服务"""
    import uvicorn
    uvicorn.run(
        "babeldoc.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()