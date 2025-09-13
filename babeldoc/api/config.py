"""
API 配置文件
"""
import os
from pathlib import Path
from typing import Optional


class Settings:
    """API 设置"""
    
    # 服务设置
    HOST: str = os.getenv("BABELDOC_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("BABELDOC_PORT", "8000"))
    DEBUG: bool = os.getenv("BABELDOC_DEBUG", "false").lower() == "true"
    
    # 安全设置
    API_KEY: Optional[str] = os.getenv("BABELDOC_API_KEY")
    ENABLE_AUTH: bool = os.getenv("BABELDOC_ENABLE_AUTH", "false").lower() == "true"
    
    # 缓存设置
    CACHE_DIR: Path = Path(os.getenv("BABELDOC_CACHE_DIR", Path.home() / ".babeldoc" / "api_cache"))
    FILE_CACHE_MAX_SIZE_GB: float = float(os.getenv("BABELDOC_FILE_CACHE_SIZE_GB", "5.0"))
    RESULT_CACHE_MAX_SIZE_GB: float = float(os.getenv("BABELDOC_RESULT_CACHE_SIZE_GB", "10.0"))
    FILE_CACHE_MAX_AGE_DAYS: int = int(os.getenv("BABELDOC_FILE_CACHE_AGE_DAYS", "1"))
    RESULT_CACHE_MAX_AGE_DAYS: int = int(os.getenv("BABELDOC_RESULT_CACHE_AGE_DAYS", "7"))
    
    # 任务设置
    MAX_CONCURRENT_TASKS: int = int(os.getenv("BABELDOC_MAX_CONCURRENT_TASKS", "3"))
    MAX_FILE_SIZE_MB: int = int(os.getenv("BABELDOC_MAX_FILE_SIZE_MB", "100"))
    
    # 日志设置
    LOG_LEVEL: str = os.getenv("BABELDOC_LOG_LEVEL", "INFO").upper()
    LOG_FILE: Optional[str] = os.getenv("BABELDOC_LOG_FILE")
    
    # OpenAI 默认设置
    DEFAULT_OPENAI_MODEL: str = os.getenv("BABELDOC_DEFAULT_MODEL", "gpt-4o-mini")
    DEFAULT_OPENAI_BASE_URL: Optional[str] = os.getenv("BABELDOC_DEFAULT_BASE_URL")
    DEFAULT_QPS: int = int(os.getenv("BABELDOC_DEFAULT_QPS", "4"))
    
    def __init__(self):
        """初始化设置，创建必要的目录"""
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)


# 全局设置实例
settings = Settings()