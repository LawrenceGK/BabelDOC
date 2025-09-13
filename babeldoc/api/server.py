#!/usr/bin/env python3
"""
BabelDOC API 服务启动脚本
"""
import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from babeldoc.api.config import settings


def setup_logging():
    """设置日志"""
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # 如果指定了日志文件
    if settings.LOG_FILE:
        file_handler = logging.FileHandler(settings.LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # 设置第三方库的日志级别
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="BabelDOC API Server")
    parser.add_argument("--host", default=settings.HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=settings.PORT, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", default=settings.DEBUG, help="Enable debug mode")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (development)")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                       default=settings.LOG_LEVEL, help="Log level")
    
    args = parser.parse_args()
    
    # 更新设置
    settings.HOST = args.host
    settings.PORT = args.port
    settings.DEBUG = args.debug
    settings.LOG_LEVEL = args.log_level
    
    # 设置日志
    setup_logging()
    
    logger = logging.getLogger(__name__)
    logger.info("启动 BabelDOC API 服务")
    logger.info(f"Host: {args.host}")
    logger.info(f"Port: {args.port}")
    logger.info(f"Debug: {args.debug}")
    logger.info(f"Cache Dir: {settings.CACHE_DIR}")
    logger.info(f"Max Concurrent Tasks: {settings.MAX_CONCURRENT_TASKS}")
    
    try:
        import uvicorn
        
        # 启动服务
        uvicorn.run(
            "babeldoc.api.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers if not args.reload else 1,  # reload mode 只能用单进程
            log_level=args.log_level.lower(),
            access_log=True,
            server_header=False,
            date_header=False
        )
        
    except ImportError:
        logger.error("缺少依赖：请安装 uvicorn")
        logger.error("运行: pip install uvicorn[standard]")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动服务失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()