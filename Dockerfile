# 使用官方 Python 基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    make \
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY babeldoc/ ./babeldoc/
COPY README.md LICENSE ./

# 安装 uv
RUN pip install uv

# 安装依赖
RUN uv sync --no-dev

# 创建必要的目录
RUN mkdir -p /app/cache /app/logs /app/work

# 设置缓存目录权限
RUN chmod 755 /app/cache /app/logs /app/work

# 暴露端口
EXPOSE 8000

# 设置默认环境变量
ENV BABELDOC_HOST=0.0.0.0
ENV BABELDOC_PORT=8000
ENV BABELDOC_CACHE_DIR=/app/cache
ENV BABELDOC_LOG_FILE=/app/logs/api.log
ENV BABELDOC_MAX_CONCURRENT_TASKS=3

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uv", "run", "python", "-m", "babeldoc.api.server"]