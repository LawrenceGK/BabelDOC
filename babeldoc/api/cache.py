"""
文件缓存管理系统
提供PDF文件和翻译结果的缓存功能
"""
import hashlib
import json
import logging
import shutil
import time
import threading
from pathlib import Path
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CacheItem:
    """缓存项"""
    def __init__(self, key: str, file_path: Path, metadata: Optional[Dict[str, Any]] = None):
        self.key = key
        self.file_path = file_path
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        self.access_count = 0

    def touch(self):
        """更新最后访问时间"""
        self.last_accessed = datetime.now()
        self.access_count += 1

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'key': self.key,
            'file_path': str(self.file_path),
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'last_accessed': self.last_accessed.isoformat(),
            'access_count': self.access_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheItem':
        """从字典创建缓存项"""
        item = cls(data['key'], Path(data['file_path']), data['metadata'])
        item.created_at = datetime.fromisoformat(data['created_at'])
        item.last_accessed = datetime.fromisoformat(data['last_accessed'])
        item.access_count = data['access_count']
        return item


class FileCache:
    """文件缓存管理器"""
    
    def __init__(
        self, 
        cache_dir: Path, 
        max_size_gb: float = 10.0, 
        max_age_days: int = 30,
        cleanup_interval_hours: int = 24
    ):
        self.cache_dir = cache_dir
        self.max_size_bytes = int(max_size_gb * 1024 * 1024 * 1024)  # 转换为字节
        self.max_age = timedelta(days=max_age_days)
        self.cleanup_interval = timedelta(hours=cleanup_interval_hours)
        
        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        
        # 内存中的缓存索引
        self.cache_index: Dict[str, CacheItem] = {}
        self._lock = threading.RLock()
        
        # 初始化
        self._load_metadata()
        self._start_cleanup_thread()

    def _generate_cache_key(self, file_content: bytes, options: Optional[Dict[str, Any]] = None) -> str:
        """生成缓存键"""
        hasher = hashlib.sha256()
        hasher.update(file_content)
        if options:
            # 将选项排序后加入hash计算，确保相同选项生成相同key
            options_str = json.dumps(options, sort_keys=True, ensure_ascii=False)
            hasher.update(options_str.encode('utf-8'))
        return hasher.hexdigest()

    def _load_metadata(self):
        """加载缓存元数据"""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item_data in data.get('items', []):
                        try:
                            item = CacheItem.from_dict(item_data)
                            # 检查文件是否存在
                            if item.file_path.exists():
                                self.cache_index[item.key] = item
                            else:
                                logger.warning(f"缓存文件不存在，忽略: {item.file_path}")
                        except Exception as e:
                            logger.error(f"加载缓存项失败: {e}")
                logger.info(f"加载了 {len(self.cache_index)} 个缓存项")
        except Exception as e:
            logger.error(f"加载缓存元数据失败: {e}")

    def _save_metadata(self):
        """保存缓存元数据"""
        try:
            data = {
                'items': [item.to_dict() for item in self.cache_index.values()],
                'updated_at': datetime.now().isoformat()
            }
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存缓存元数据失败: {e}")

    def _get_cache_size(self) -> int:
        """获取缓存总大小"""
        total_size = 0
        for item in self.cache_index.values():
            if item.file_path.exists():
                total_size += item.file_path.stat().st_size
        return total_size

    def _cleanup_old_files(self):
        """清理过期文件"""
        with self._lock:
            current_time = datetime.now()
            to_remove = []
            
            for key, item in self.cache_index.items():
                # 检查文件是否过期
                if current_time - item.created_at > self.max_age:
                    to_remove.append(key)
                    continue
                
                # 检查文件是否存在
                if not item.file_path.exists():
                    to_remove.append(key)
            
            # 删除过期或不存在的文件
            for key in to_remove:
                item = self.cache_index.pop(key)
                if item.file_path.exists():
                    try:
                        if item.file_path.is_dir():
                            shutil.rmtree(item.file_path)
                        else:
                            item.file_path.unlink()
                        logger.debug(f"删除过期缓存文件: {item.file_path}")
                    except Exception as e:
                        logger.error(f"删除缓存文件失败: {e}")
            
            if to_remove:
                logger.info(f"清理了 {len(to_remove)} 个过期缓存项")
                self._save_metadata()

    def _cleanup_by_size(self):
        """按大小清理缓存"""
        with self._lock:
            current_size = self._get_cache_size()
            
            if current_size <= self.max_size_bytes:
                return
            
            # 按最后访问时间排序，删除最久未访问的文件
            items_by_access = sorted(
                self.cache_index.items(),
                key=lambda x: x[1].last_accessed
            )
            
            target_size = int(self.max_size_bytes * 0.8)  # 清理到80%容量
            removed_count = 0
            
            for key, item in items_by_access:
                if current_size <= target_size:
                    break
                
                try:
                    if item.file_path.exists():
                        file_size = item.file_path.stat().st_size
                        if item.file_path.is_dir():
                            shutil.rmtree(item.file_path)
                        else:
                            item.file_path.unlink()
                        current_size -= file_size
                    
                    del self.cache_index[key]
                    removed_count += 1
                    logger.debug(f"删除缓存文件以释放空间: {item.file_path}")
                
                except Exception as e:
                    logger.error(f"删除缓存文件失败: {e}")
            
            if removed_count > 0:
                logger.info(f"为释放空间清理了 {removed_count} 个缓存项")
                self._save_metadata()

    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_worker():
            while True:
                try:
                    self._cleanup_old_files()
                    self._cleanup_by_size()
                    time.sleep(self.cleanup_interval.total_seconds())
                except Exception as e:
                    logger.error(f"缓存清理线程出错: {e}")
                    time.sleep(3600)  # 出错时等待1小时后重试
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.info("启动缓存清理线程")

    def get_cache_key(self, file_content: bytes, options: Optional[Dict[str, Any]] = None) -> str:
        """获取缓存键"""
        return self._generate_cache_key(file_content, options)

    def exists(self, cache_key: str) -> bool:
        """检查缓存是否存在"""
        with self._lock:
            if cache_key not in self.cache_index:
                return False
            
            item = self.cache_index[cache_key]
            if not item.file_path.exists():
                # 文件不存在，从索引中删除
                del self.cache_index[cache_key]
                self._save_metadata()
                return False
            
            return True

    def get(self, cache_key: str) -> Optional[Path]:
        """获取缓存文件路径"""
        with self._lock:
            if not self.exists(cache_key):
                return None
            
            item = self.cache_index[cache_key]
            item.touch()  # 更新访问时间
            self._save_metadata()
            return item.file_path

    def put(self, cache_key: str, file_path: Path, metadata: Optional[Dict[str, Any]] = None, copy_file: bool = True) -> Path:
        """添加文件到缓存"""
        with self._lock:
            # 生成缓存文件路径
            cache_file_path = self.cache_dir / f"{cache_key}"
            
            # 如果是目录，需要特殊处理
            if file_path.is_dir():
                cache_file_path = self.cache_dir / f"{cache_key}_dir"
                if copy_file:
                    if cache_file_path.exists():
                        shutil.rmtree(cache_file_path)
                    shutil.copytree(file_path, cache_file_path)
            else:
                # 获取原文件扩展名
                suffix = file_path.suffix
                cache_file_path = self.cache_dir / f"{cache_key}{suffix}"
                
                if copy_file:
                    shutil.copy2(file_path, cache_file_path)
            
            # 创建缓存项
            item = CacheItem(cache_key, cache_file_path, metadata)
            self.cache_index[cache_key] = item
            
            # 检查是否需要清理空间
            if self._get_cache_size() > self.max_size_bytes:
                self._cleanup_by_size()
            
            self._save_metadata()
            logger.debug(f"添加文件到缓存: {cache_file_path}")
            return cache_file_path

    def delete(self, cache_key: str) -> bool:
        """删除缓存项"""
        with self._lock:
            if cache_key not in self.cache_index:
                return False
            
            item = self.cache_index.pop(cache_key)
            
            try:
                if item.file_path.exists():
                    if item.file_path.is_dir():
                        shutil.rmtree(item.file_path)
                    else:
                        item.file_path.unlink()
                
                self._save_metadata()
                logger.debug(f"删除缓存项: {item.file_path}")
                return True
            
            except Exception as e:
                logger.error(f"删除缓存文件失败: {e}")
                return False

    def list_cache_items(self) -> List[Dict[str, Any]]:
        """列出所有缓存项"""
        with self._lock:
            items = []
            for item in self.cache_index.values():
                item_dict = item.to_dict()
                if item.file_path.exists():
                    if item.file_path.is_dir():
                        # 计算目录大小
                        size = sum(f.stat().st_size for f in item.file_path.rglob('*') if f.is_file())
                    else:
                        size = item.file_path.stat().st_size
                    item_dict['size'] = size
                    items.append(item_dict)
            return items

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_size = self._get_cache_size()
            total_items = len(self.cache_index)
            
            return {
                'total_items': total_items,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'max_size_gb': self.max_size_bytes / (1024 * 1024 * 1024),
                'usage_percent': round((total_size / self.max_size_bytes) * 100, 2) if self.max_size_bytes > 0 else 0,
                'cache_dir': str(self.cache_dir),
                'max_age_days': self.max_age.days
            }

    def clear_all(self):
        """清空所有缓存"""
        with self._lock:
            for item in self.cache_index.values():
                try:
                    if item.file_path.exists():
                        if item.file_path.is_dir():
                            shutil.rmtree(item.file_path)
                        else:
                            item.file_path.unlink()
                except Exception as e:
                    logger.error(f"删除缓存文件失败: {e}")
            
            self.cache_index.clear()
            self._save_metadata()
            logger.info("清空所有缓存")


# 全局缓存实例
_cache_instances: Dict[str, FileCache] = {}
_cache_lock = threading.Lock()


def get_cache(name: str = 'default', **kwargs) -> FileCache:
    """获取或创建缓存实例"""
    with _cache_lock:
        if name not in _cache_instances:
            from babeldoc.const import CACHE_FOLDER
            cache_dir = Path(CACHE_FOLDER) / name
            _cache_instances[name] = FileCache(cache_dir, **kwargs)
        return _cache_instances[name]