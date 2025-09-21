"""
API 数据模型
定义 FastAPI 服务的请求和响应模型
"""
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Annotated
from datetime import datetime
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"          # 等待中
    PROCESSING = "processing"    # 处理中
    COMPLETED = "completed"      # 完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 已取消


class WatermarkMode(str, Enum):
    """水印模式"""
    WATERMARKED = "watermarked"
    NO_WATERMARK = "no_watermark"
    BOTH = "both"


class OutputFileType(str, Enum):
    """输出文件类型"""
    MONO = "mono"                    # 仅译文版本
    DUAL = "dual"                    # 双语版本
    MONO_NO_WATERMARK = "mono_no_watermark"    # 仅译文无水印版本
    DUAL_NO_WATERMARK = "dual_no_watermark"    # 双语无水印版本
    GLOSSARY = "glossary"           # 词汇表文件


class OutputFileInfo(BaseModel):
    """输出文件信息"""
    file_path: str = Field(description="文件路径")
    file_type: OutputFileType = Field(description="文件类型")
    file_size: int = Field(description="文件大小（字节）")
    created_at: datetime = Field(description="创建时间")
    watermark: bool = Field(description="是否包含水印")
    
    @classmethod
    def from_file_path(cls, file_path: str) -> "OutputFileInfo":
        """从文件路径推断文件类型"""
        path = Path(file_path)
        file_name = path.name.lower()
        
        # 根据文件名推断文件类型
        if file_name.endswith('.glossary.csv'):
            file_type = OutputFileType.GLOSSARY
            watermark = False
        elif '.no_watermark.' in file_name:
            if '.mono.' in file_name:
                file_type = OutputFileType.MONO_NO_WATERMARK
            elif '.dual.' in file_name:
                file_type = OutputFileType.DUAL_NO_WATERMARK
            else:
                file_type = OutputFileType.MONO_NO_WATERMARK  # 默认
            watermark = False
        elif '.mono.' in file_name:
            file_type = OutputFileType.MONO
            watermark = True
        elif '.dual.' in file_name:
            file_type = OutputFileType.DUAL
            watermark = True
        else:
            # 兜底逻辑：默认为仅译文版本
            file_type = OutputFileType.MONO
            watermark = True
        
        file_size = path.stat().st_size if path.exists() else 0
        
        return cls(
            file_path=str(file_path),
            file_type=file_type,
            file_size=file_size,
            created_at=datetime.now(),
            watermark=watermark
        )


class TranslationRequest(BaseModel):
    """翻译请求模型"""
    # 基本设置
    lang_in: str = Field(default="en", description="源语言代码")
    lang_out: str = Field(default="zh", description="目标语言代码")
    
    # 页面设置
    pages: Optional[str] = Field(default=None, description="要翻译的页面范围，如: 1,2,1-,-3,3-5")
    min_text_length: int = Field(default=5, description="最小翻译文本长度")
    
    # 输出设置
    no_dual: bool = Field(default=False, description="不输出双语PDF")
    no_mono: bool = Field(default=False, description="不输出单语PDF")
    dual_translate_first: bool = Field(default=False, description="双语PDF中译文优先")
    use_alternating_pages_dual: bool = Field(default=False, description="使用交替页面模式")
    watermark_output_mode: WatermarkMode = Field(default=WatermarkMode.WATERMARKED, description="水印输出模式")
    
    # 公式和格式处理
    formular_font_pattern: Optional[str] = Field(default=None, description="公式字体模式")
    formular_char_pattern: Optional[str] = Field(default=None, description="公式字符模式")
    skip_formula_offset_calculation: bool = Field(default=False, description="跳过公式偏移计算")
    
    # 兼容性设置
    enhance_compatibility: bool = Field(default=False, description="增强兼容性")
    skip_clean: bool = Field(default=False, description="跳过PDF清理")
    disable_rich_text_translate: bool = Field(default=False, description="禁用富文本翻译")
    
    # 分段设置
    split_short_lines: bool = Field(default=False, description="强制分割短行")
    short_line_split_factor: float = Field(default=0.8, description="短行分割因子")
    
    # 表格和扫描处理
    translate_table_text: bool = Field(default=False, description="翻译表格文本（实验性）")
    skip_scanned_detection: bool = Field(default=False, description="跳过扫描文档检测")
    ocr_workaround: bool = Field(default=False, description="OCR变通方案")
    auto_enable_ocr_workaround: bool = Field(default=False, description="自动启用OCR变通方案")
    
    # 高级设置
    custom_system_prompt: Optional[str] = Field(default=None, description="自定义系统提示")
    show_char_box: bool = Field(default=False, description="显示字符框（调试用）")
    max_pages_per_part: Optional[int] = Field(default=None, description="每部分最大页数")
    
    # 图形元素处理
    enable_graphic_element_process: bool = Field(default=True, description="启用图形元素处理")
    remove_non_formula_lines: bool = Field(default=False, description="移除非公式线条")
    figure_table_protection_threshold: float = Field(default=0.9, description="图表保护阈值")
    non_formula_line_iou_threshold: float = Field(default=0.5, description="非公式线条IoU阈值")
    
    # 词汇表设置
    glossary_files: Optional[str] = Field(default=None, description="词汇表文件路径，多个用逗号分隔")
    auto_extract_glossary: bool = Field(default=False, description="自动提取词汇表")
    
    # 渲染设置  
    skip_form_render: bool = Field(default=False, description="跳过表单渲染")
    skip_curve_render: bool = Field(default=False, description="跳过曲线渲染")
    merge_alternating_line_numbers: bool = Field(default=True, description="合并交替行号")
    
    # 解析设置
    skip_translation: bool = Field(default=False, description="跳过翻译（仅解析）")
    only_parse_generate_pdf: bool = Field(default=False, description="仅解析生成PDF")
    
    # OpenAI 设置
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI 模型")
    openai_base_url: Optional[str] = Field(default=None, description="OpenAI API 基础URL")
    openai_api_key: str = Field(description="OpenAI API 密钥")
    qps: int = Field(default=4, description="QPS限制")
    enable_json_mode_if_requested: bool = Field(default=False, description="如果请求则启用JSON模式")
    send_dashscope_header: bool = Field(default=False, description="发送DashScope头")
    no_send_temperature: bool = Field(default=False, description="不发送temperature参数")
    
    # 其他设置
    ignore_cache: bool = Field(default=False, description="忽略翻译缓存")
    working_dir: Optional[str] = Field(default=None, description="工作目录")


class TranslationResponse(BaseModel):
    """翻译响应模型"""
    task_id: str = Field(description="任务ID")
    status: TaskStatus = Field(description="任务状态")
    message: str = Field(description="状态消息")
    estimated_time: Optional[int] = Field(default=None, description="预估完成时间（秒）")


class TaskInfo(BaseModel):
    """任务信息模型"""
    task_id: str = Field(description="任务ID")
    status: TaskStatus = Field(description="任务状态")
    progress: float = Field(default=0.0, description="进度百分比 (0-100)")
    message: str = Field(default="", description="状态消息")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")
    estimated_time: Optional[int] = Field(default=None, description="预估剩余时间（秒）")
    
    # 文件信息
    input_filename: str = Field(description="输入文件名")
    input_file_size: int = Field(description="输入文件大小（字节）")
    output_files: List[OutputFileInfo] = Field(default=[], description="输出文件列表")
    
    # 向后兼容：保留原有的字符串列表格式（已弃用，但保留以支持老客户端）
    output_file_paths: List[str] = Field(default=[], description="输出文件路径列表（已弃用）")
    
    # 翻译设置
    lang_in: str = Field(description="源语言")
    lang_out: str = Field(description="目标语言")
    pages: Optional[str] = Field(default=None, description="翻译页面范围")
    
    # 错误信息
    error_message: Optional[str] = Field(default=None, description="错误消息")
    error_traceback: Optional[str] = Field(default=None, description="错误堆栈")
    
    def get_file_by_type(self, file_type: OutputFileType) -> Optional[OutputFileInfo]:
        """根据文件类型获取输出文件"""
        for file_info in self.output_files:
            if file_info.file_type == file_type:
                return file_info
        return None
    
    def get_files_by_type(self, file_type: OutputFileType) -> List[OutputFileInfo]:
        """根据文件类型获取所有匹配的输出文件"""
        return [file_info for file_info in self.output_files if file_info.file_type == file_type]
    
    def has_file_type(self, file_type: OutputFileType) -> bool:
        """检查是否存在指定类型的文件"""
        return any(file_info.file_type == file_type for file_info in self.output_files)


class TaskListResponse(BaseModel):
    """任务列表响应模型"""
    tasks: List[TaskInfo] = Field(description="任务列表")
    total: int = Field(description="总任务数")
    page: int = Field(description="当前页号")
    page_size: int = Field(description="每页大小")


class FileUploadResponse(BaseModel):
    """文件上传响应模型"""
    file_id: str = Field(description="文件ID")
    filename: str = Field(description="文件名")
    file_size: int = Field(description="文件大小")
    uploaded_at: datetime = Field(description="上传时间")
    expires_at: datetime = Field(description="过期时间")


class CacheStats(BaseModel):
    """缓存统计模型"""
    total_items: int = Field(description="缓存项总数")
    total_size_bytes: int = Field(description="缓存总大小（字节）")
    total_size_mb: float = Field(description="缓存总大小（MB）")
    max_size_gb: float = Field(description="最大缓存大小（GB）")
    usage_percent: float = Field(description="使用率百分比")
    cache_dir: str = Field(description="缓存目录")
    max_age_days: int = Field(description="最大缓存天数")


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str = Field(description="服务状态")
    version: str = Field(description="版本号")
    uptime: float = Field(description="运行时间（秒）")
    cache_stats: CacheStats = Field(description="缓存统计")
    system_info: Dict[str, Any] = Field(description="系统信息")


class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str = Field(description="错误类型")
    message: str = Field(description="错误消息")
    detail: Optional[str] = Field(default=None, description="详细信息")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")


class ConfigResponse(BaseModel):
    """配置响应模型"""
    supported_languages: Dict[str, str] = Field(description="支持的语言")
    default_settings: TranslationRequest = Field(description="默认设置")
    limits: Dict[str, Any] = Field(description="限制信息")
    output_options: Optional[Dict[str, Any]] = Field(default=None, description="输出选项配置")


class ProgressUpdate(BaseModel):
    """进度更新模型（WebSocket）"""
    task_id: str = Field(description="任务ID")
    progress: float = Field(description="进度百分比")
    message: str = Field(description="状态消息")
    stage: str = Field(description="当前阶段")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")


class BatchDownloadRequest(BaseModel):
    """批量下载请求模型"""
    task_ids: Annotated[List[str], Field(description="任务ID列表", min_length=1, max_length=50)]
    file_types: Optional[List[OutputFileType]] = Field(
        default=None,
        description="要下载的文件类型列表。如果为空，默认下载所有可用文件"
    )
    include_original: bool = Field(default=False, description="是否包含原文件")
    watermark: Optional[bool] = Field(default=None, description="是否下载有水印版本。None表示都下载")
    archive_name: Optional[str] = Field(default=None, description="压缩包名称（不含扩展名）")


class BatchDownloadFileInfo(BaseModel):
    """批量下载文件信息"""
    task_id: str = Field(description="任务ID")
    file_name: str = Field(description="文件名")
    file_type: OutputFileType = Field(description="文件类型")
    file_size: int = Field(description="文件大小（字节）")
    watermark: bool = Field(description="是否包含水印")
    status: str = Field(description="文件状态（success/failed/not_found）")
    error_message: Optional[str] = Field(default=None, description="错误信息")


class BatchDownloadResponse(BaseModel):
    """批量下载响应模型"""
    batch_id: str = Field(description="批量下载批次ID")
    total_files: int = Field(description="总文件数")
    successful_files: int = Field(description="成功文件数")
    failed_files: int = Field(description="失败文件数")
    total_size: int = Field(description="总文件大小（字节）")
    archive_size: int = Field(description="压缩包大小（字节）")
    files: List[BatchDownloadFileInfo] = Field(description="文件详细信息")
    download_url: str = Field(description="下载链接")
    expires_at: datetime = Field(description="下载链接过期时间")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")