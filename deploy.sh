#!/bin/bash
# BabelDOC API 服务部署脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# 检查 Docker 和 Docker Compose
check_dependencies() {
    log "检查依赖..."
    
    if ! command -v docker &> /dev/null; then
        error "Docker 未安装。请先安装 Docker。"
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose 未安装。请先安装 Docker Compose。"
    fi
    
    log "依赖检查完成"
}

# 创建必要的目录
create_directories() {
    log "创建目录结构..."
    
    mkdir -p cache logs
    chmod 755 cache logs
    
    log "目录创建完成"
}

# 构建镜像
build_image() {
    log "构建 Docker 镜像..."
    
    if [[ "$1" == "--no-cache" ]]; then
        docker-compose build --no-cache
    else
        docker-compose build
    fi
    
    log "镜像构建完成"
}

# 启动服务
start_services() {
    log "启动服务..."
    
    docker-compose up -d
    
    log "服务启动完成"
}

# 停止服务
stop_services() {
    log "停止服务..."
    
    docker-compose down
    
    log "服务已停止"
}

# 查看服务状态
check_status() {
    log "检查服务状态..."
    
    docker-compose ps
    
    # 检查健康状态
    echo ""
    log "健康检查..."
    
    if curl -s http://localhost:8000/health > /dev/null; then
        log "API 服务运行正常"
    else
        warn "API 服务可能未正常启动，请检查日志"
    fi
}

# 查看日志
show_logs() {
    docker-compose logs -f babeldoc-api
}

# 清理资源
cleanup() {
    log "清理资源..."
    
    # 停止并删除容器
    docker-compose down --volumes --remove-orphans
    
    # 删除镜像（可选）
    if [[ "$1" == "--remove-images" ]]; then
        docker-compose down --rmi all
    fi
    
    log "清理完成"
}

# 更新服务
update_service() {
    log "更新服务..."
    
    # 拉取最新代码（如果是 git 仓库）
    if [[ -d ".git" ]]; then
        git pull
    fi
    
    # 重新构建镜像
    build_image --no-cache
    
    # 重启服务
    docker-compose down
    start_services
    
    log "服务更新完成"
}

# 备份数据
backup_data() {
    local backup_dir="backup_$(date +%Y%m%d_%H%M%S)"
    
    log "备份数据到 $backup_dir..."
    
    mkdir -p "$backup_dir"
    cp -r cache logs "$backup_dir/"
    
    # 导出数据库（如果使用）
    # docker-compose exec postgres pg_dump -U user database > "$backup_dir/database.sql"
    
    log "备份完成: $backup_dir"
}

# 恢复数据
restore_data() {
    local backup_dir="$1"
    
    if [[ -z "$backup_dir" ]]; then
        error "请指定备份目录"
    fi
    
    if [[ ! -d "$backup_dir" ]]; then
        error "备份目录不存在: $backup_dir"
    fi
    
    log "从 $backup_dir 恢复数据..."
    
    # 停止服务
    docker-compose down
    
    # 恢复文件
    cp -r "$backup_dir/cache" "$backup_dir/logs" ./
    
    # 启动服务
    start_services
    
    log "数据恢复完成"
}

# 显示帮助
show_help() {
    echo "BabelDOC API 部署脚本"
    echo ""
    echo "用法: $0 [命令] [选项]"
    echo ""
    echo "命令:"
    echo "  build                 构建 Docker 镜像"
    echo "  build --no-cache      无缓存构建镜像"
    echo "  start                 启动服务"
    echo "  stop                  停止服务"
    echo "  restart               重启服务"
    echo "  status                查看服务状态"
    echo "  logs                  查看实时日志"
    echo "  update                更新服务"
    echo "  cleanup               清理资源"
    echo "  cleanup --remove-images  清理资源并删除镜像"
    echo "  backup                备份数据"
    echo "  restore <备份目录>     恢复数据"
    echo "  help                  显示此帮助"
    echo ""
    echo "示例:"
    echo "  $0 build              # 构建镜像"
    echo "  $0 start              # 启动服务"
    echo "  $0 status             # 查看状态"
    echo "  $0 logs               # 查看日志"
}

# 主函数
main() {
    case "$1" in
        "build")
            check_dependencies
            create_directories
            build_image "$2"
            ;;
        "start")
            check_dependencies
            create_directories
            start_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            stop_services
            start_services
            ;;
        "status")
            check_status
            ;;
        "logs")
            show_logs
            ;;
        "update")
            check_dependencies
            update_service
            ;;
        "cleanup")
            cleanup "$2"
            ;;
        "backup")
            backup_data
            ;;
        "restore")
            restore_data "$2"
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        "")
            log "启动 BabelDOC API 服务..."
            check_dependencies
            create_directories
            build_image
            start_services
            check_status
            ;;
        *)
            error "未知命令: $1. 使用 '$0 help' 查看帮助。"
            ;;
    esac
}

# 执行主函数
main "$@"