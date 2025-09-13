# BabelDOC API 服务

这是 BabelDOC PDF 翻译工具的 FastAPI 服务版本，提供了完整的 HTTP API 接口，支持文件缓存和异步翻译任务处理。

## 功能特点

- ✅ **RESTful API**: 完整的 HTTP API 接口
- ✅ **异步处理**: 支持异步翻译任务
- ✅ **文件缓存**: 智能的文件缓存系统
- ✅ **进度监控**: 实时翻译进度跟踪
- ✅ **多任务并发**: 支持多个翻译任务并发执行
- ✅ **WebSocket 支持**: 实时进度推送
- ✅ **自动清理**: 自动清理过期缓存和任务
- ✅ **健康检查**: 服务健康状态监控
- ✅ **配置灵活**: 丰富的配置选项

## 安装依赖

```bash
# 安装 BabelDOC 及 FastAPI 相关依赖
pip install -e .

# 或者使用 uv（推荐）
uv sync
```

## 快速启动

### 1. 基本启动

```bash
# 使用默认配置启动
python -m babeldoc.api.server

# 或者使用命令行工具
babeldoc-api
```

### 2. 自定义配置启动

```bash
# 指定主机和端口
python -m babeldoc.api.server --host 0.0.0.0 --port 8080

# 启用调试模式
python -m babeldoc.api.server --debug

# 指定日志级别
python -m babeldoc.api.server --log-level DEBUG
```

### 3. 环境变量配置

```bash
# 设置环境变量
export BABELDOC_HOST=0.0.0.0
export BABELDOC_PORT=8080
export BABELDOC_MAX_CONCURRENT_TASKS=5
export BABELDOC_CACHE_DIR=/path/to/cache
export OPENAI_API_KEY=your_openai_api_key

# 启动服务
python -m babeldoc.api.server
```

## API 接口文档

服务启动后，访问以下地址查看 API 文档：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## 主要 API 端点

### 基础端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 服务信息 |
| `/health` | GET | 健康检查 |
| `/config` | GET | 配置信息 |

### 文件管理

| 端点 | 方法 | 描述 |
|------|------|------|
| `/upload` | POST | 上传PDF文件 |

### 翻译任务

| 端点 | 方法 | 描述 |
|------|------|------|
| `/translate` | POST | 提交翻译任务 |
| `/tasks` | GET | 获取任务列表 |
| `/tasks/{task_id}` | GET | 获取任务状态 |
| `/tasks/{task_id}` | DELETE | 删除任务 |
| `/tasks/{task_id}/cancel` | POST | 取消任务 |
| `/tasks/{task_id}/download` | GET | 下载翻译结果 |

### 缓存管理

| 端点 | 方法 | 描述 |
|------|------|------|
| `/cache/stats` | GET | 缓存统计信息 |
| `/cache/clear` | DELETE | 清空缓存 |

### WebSocket

| 端点 | 协议 | 描述 |
|------|------|------|
| `/ws/{task_id}` | WebSocket | 实时进度推送 |

## 使用示例

### 1. 基本翻译示例

```python
import requests

# 1. 上传文件
with open("document.pdf", "rb") as f:
    files = {"file": f}
    response = requests.post("http://localhost:8000/upload", files=files)
    file_id = response.json()["file_id"]

# 2. 提交翻译任务
translation_request = {
    "lang_in": "en",
    "lang_out": "zh",
    "openai_api_key": "your_openai_api_key",
    "openai_model": "gpt-4o-mini"
}
response = requests.post(
    "http://localhost:8000/translate",
    json=translation_request,
    data={"file_id": file_id}
)
task_id = response.json()["task_id"]

# 3. 查询任务状态
response = requests.get(f"http://localhost:8000/tasks/{task_id}")
task_info = response.json()
print(f"任务状态: {task_info['status']}")
print(f"进度: {task_info['progress']}%")

# 4. 下载结果（任务完成后）
if task_info["status"] == "completed":
    response = requests.get(f"http://localhost:8000/tasks/{task_id}/download")
    with open("translated.pdf", "wb") as f:
        f.write(response.content)
```

### 2. 直接上传并翻译

```python
import requests

# 直接上传文件并翻译
with open("document.pdf", "rb") as f:
    files = {"file": f}
    data = {
        "lang_in": "en",
        "lang_out": "zh",
        "openai_api_key": "your_openai_api_key",
        "no_dual": "false",
        "no_mono": "false"
    }
    response = requests.post("http://localhost:8000/translate", files=files, data=data)
    task_id = response.json()["task_id"]
    print(f"翻译任务已创建: {task_id}")
```

### 3. WebSocket 实时进度监控

```python
import asyncio
import websockets
import json

async def monitor_progress(task_id):
    uri = f"ws://localhost:8000/ws/{task_id}"
    
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            print(f"进度: {data['progress']:.1f}% - {data['message']}")
            
            if data.get('status') in ['completed', 'failed', 'cancelled']:
                break

# 使用示例
asyncio.run(monitor_progress("your_task_id"))
```

### 4. 高级翻译选项

```python
import requests

advanced_request = {
    "lang_in": "en",
    "lang_out": "zh",
    "openai_api_key": "your_openai_api_key",
    "openai_model": "gpt-4o",
    "pages": "1-10",  # 只翻译前10页
    "no_dual": False,  # 输出双语PDF
    "watermark_output_mode": "no_watermark",  # 无水印
    "enhance_compatibility": True,  # 增强兼容性
    "translate_table_text": True,  # 翻译表格文本
    "custom_system_prompt": "请保持学术论文的正式语调",  # 自定义提示
    "qps": 2  # 降低请求频率
}

with open("academic_paper.pdf", "rb") as f:
    files = {"file": f}
    response = requests.post(
        "http://localhost:8000/translate", 
        files=files, 
        data={k: str(v) for k, v in advanced_request.items()}
    )
```

## 配置选项

### 环境变量

| 变量名 | 默认值 | 描述 |
|--------|--------|------|
| `BABELDOC_HOST` | `0.0.0.0` | 服务监听地址 |
| `BABELDOC_PORT` | `8000` | 服务端口 |
| `BABELDOC_DEBUG` | `false` | 调试模式 |
| `BABELDOC_MAX_CONCURRENT_TASKS` | `3` | 最大并发任务数 |
| `BABELDOC_MAX_FILE_SIZE_MB` | `100` | 最大文件大小(MB) |
| `BABELDOC_CACHE_DIR` | `~/.babeldoc/api_cache` | 缓存目录 |
| `BABELDOC_FILE_CACHE_SIZE_GB` | `5.0` | 文件缓存大小(GB) |
| `BABELDOC_RESULT_CACHE_SIZE_GB` | `10.0` | 结果缓存大小(GB) |
| `BABELDOC_FILE_CACHE_AGE_DAYS` | `1` | 文件缓存保留天数 |
| `BABELDOC_RESULT_CACHE_AGE_DAYS` | `7` | 结果缓存保留天数 |
| `BABELDOC_LOG_LEVEL` | `INFO` | 日志级别 |
| `BABELDOC_LOG_FILE` | 无 | 日志文件路径 |

### 翻译参数

支持所有 BabelDOC 命令行工具的参数，包括：

- **基础参数**: `lang_in`, `lang_out`, `pages`, `min_text_length`
- **输出控制**: `no_dual`, `no_mono`, `watermark_output_mode`
- **兼容性**: `enhance_compatibility`, `skip_clean`, `disable_rich_text_translate`
- **高级功能**: `translate_table_text`, `custom_system_prompt`, `formular_font_pattern`
- **性能调优**: `qps`, `max_pages_per_part`, `skip_scanned_detection`

## Docker 部署

### 1. 构建镜像

```bash
# 在项目根目录下
docker build -t babeldoc-api .
```

### 2. 运行容器

```bash
# 基本运行
docker run -p 8000:8000 babeldoc-api

# 挂载缓存目录
docker run -p 8000:8000 -v /host/cache:/app/cache babeldoc-api

# 环境变量配置
docker run -p 8000:8000 \
  -e BABELDOC_MAX_CONCURRENT_TASKS=5 \
  -e BABELDOC_CACHE_DIR=/app/cache \
  babeldoc-api
```

### 3. docker-compose

```yaml
version: '3.8'

services:
  babeldoc-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - BABELDOC_MAX_CONCURRENT_TASKS=5
      - BABELDOC_CACHE_DIR=/app/cache
    volumes:
      - ./cache:/app/cache
      - ./logs:/app/logs
    restart: unless-stopped
```

## 生产环境部署

### 1. 使用 Gunicorn

```bash
# 安装 gunicorn
pip install gunicorn

# 启动服务
gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 300 \
  --keep-alive 2 \
  --max-requests 1000 \
  babeldoc.api.main:app
```

### 2. Nginx 反向代理

```nginx
upstream babeldoc_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    
    client_max_body_size 100M;
    
    location / {
        proxy_pass http://babeldoc_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
    
    location /ws/ {
        proxy_pass http://babeldoc_api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 3. Systemd 服务

```ini
# /etc/systemd/system/babeldoc-api.service
[Unit]
Description=BabelDOC API Service
After=network.target

[Service]
Type=exec
User=babeldoc
Group=babeldoc
WorkingDirectory=/opt/babeldoc
Environment=PATH=/opt/babeldoc/venv/bin
Environment=BABELDOC_CACHE_DIR=/opt/babeldoc/cache
Environment=BABELDOC_LOG_FILE=/opt/babeldoc/logs/api.log
ExecStart=/opt/babeldoc/venv/bin/python -m babeldoc.api.server
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 监控和日志

### 1. 健康检查

```bash
# 检查服务状态
curl http://localhost:8000/health

# 检查缓存状态
curl http://localhost:8000/cache/stats
```

### 2. 日志配置

```python
# 在启动前设置日志
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/path/to/babeldoc-api.log'),
        logging.StreamHandler()
    ]
)
```

## 故障排除

### 常见问题

1. **内存不足**
   - 调整 `MAX_CONCURRENT_TASKS` 降低并发数
   - 增加系统内存或使用交换空间

2. **磁盘空间不足**
   - 检查缓存目录空间
   - 调整缓存大小限制
   - 手动清理 `/cache/clear`

3. **翻译超时**
   - 检查 OpenAI API 连接
   - 调整 QPS 限制
   - 检查文档大小和复杂度

4. **端口占用**
   - 使用 `netstat -tlnp | grep 8000` 查看端口占用
   - 更改端口或停止冲突服务

### 调试模式

```bash
# 启用详细日志
python -m babeldoc.api.server --debug --log-level DEBUG

# 查看详细错误信息
tail -f /path/to/babeldoc-api.log
```

## 安全建议

1. **API 密钥管理**
   - 不要在代码中硬编码 API 密钥
   - 使用环境变量或密钥管理服务
   - 定期轮换 API 密钥

2. **网络安全**
   - 使用 HTTPS 加密传输
   - 限制访问 IP 地址
   - 配置防火墙规则

3. **文件安全**
   - 验证上传文件类型和大小
   - 定期清理临时文件
   - 设置适当的文件权限

## 贡献指南

欢迎提交问题报告和功能请求到 [GitHub Issues](https://github.com/funstory-ai/BabelDOC/issues)。

## 许可证

本项目使用 AGPL-3.0 许可证。详见 [LICENSE](LICENSE) 文件。