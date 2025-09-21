"""
API工具函数
提供批量下载、文件处理等通用功能
"""
import os
import uuid
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class BatchDownloadManager:
    """批量下载管理器"""
    
    def __init__(self, temp_dir: Optional[str] = None):
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir()) / "babeldoc_batch"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.batch_cache = {}  # 存储批次信息
        
    def create_zip_archive(
        self, 
        files: List[Dict[str, str]], 
        archive_name: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> Tuple[str, str, int]:
        """
        创建ZIP压缩包
        
        Args:
            files: 文件列表，每个元素包含 {'source_path': str, 'archive_name': str}
            archive_name: 压缩包名称（不含扩展名）
            batch_id: 批次ID
            
        Returns:
            Tuple[zip_path, batch_id, total_size]
        """
        if not batch_id:
            batch_id = str(uuid.uuid4())
            
        if not archive_name:
            archive_name = f"babeldoc_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
        # 清理文件名
        safe_archive_name = self._sanitize_filename(archive_name)
        zip_filename = f"{safe_archive_name}_{batch_id[:8]}.zip"
        zip_path = self.temp_dir / zip_filename
        
        total_size = 0
        successful_files = 0
        failed_files = []
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_info in files:
                    source_path = Path(file_info['source_path'])
                    archive_name = file_info['archive_name']
                    
                    if not source_path.exists():
                        failed_files.append({
                            'file': archive_name,
                            'error': 'File not found'
                        })
                        continue
                        
                    try:
                        # 添加文件到压缩包
                        zipf.write(source_path, archive_name)
                        file_size = source_path.stat().st_size
                        total_size += file_size
                        successful_files += 1
                        
                        logger.debug(f"Added file to archive: {archive_name} ({file_size} bytes)")
                        
                    except Exception as e:
                        failed_files.append({
                            'file': archive_name,
                            'error': str(e)
                        })
                        logger.error(f"Failed to add file {archive_name} to archive: {e}")
                        
            archive_size = zip_path.stat().st_size
            
            # 保存批次信息
            self.batch_cache[batch_id] = {
                'zip_path': str(zip_path),
                'created_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(hours=24),  # 24小时后过期
                'total_files': len(files),
                'successful_files': successful_files,
                'failed_files': failed_files,
                'total_size': total_size,
                'archive_size': archive_size
            }
            
            logger.info(f"Created batch archive: {zip_path} ({archive_size} bytes, {successful_files}/{len(files)} files)")
            
            return str(zip_path), batch_id, archive_size
            
        except Exception as e:
            logger.error(f"Failed to create archive: {e}")
            # 清理失败的文件
            if zip_path.exists():
                zip_path.unlink()
            raise
    
    def get_batch_info(self, batch_id: str) -> Optional[Dict]:
        """获取批次信息"""
        batch_info = self.batch_cache.get(batch_id)
        if not batch_info:
            return None
            
        # 检查是否过期
        if datetime.now() > batch_info['expires_at']:
            self.cleanup_batch(batch_id)
            return None
            
        return batch_info
    
    def cleanup_batch(self, batch_id: str) -> bool:
        """清理批次文件"""
        batch_info = self.batch_cache.get(batch_id)
        if not batch_info:
            return False
            
        try:
            zip_path = Path(batch_info['zip_path'])
            if zip_path.exists():
                zip_path.unlink()
                logger.info(f"Cleaned up batch file: {zip_path}")
                
            del self.batch_cache[batch_id]
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup batch {batch_id}: {e}")
            return False
    
    def cleanup_expired_batches(self) -> int:
        """清理过期的批次文件"""
        now = datetime.now()
        expired_batches = []
        
        for batch_id, batch_info in self.batch_cache.items():
            if now > batch_info['expires_at']:
                expired_batches.append(batch_id)
                
        cleaned_count = 0
        for batch_id in expired_batches:
            if self.cleanup_batch(batch_id):
                cleaned_count += 1
                
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} expired batch files")
            
        return cleaned_count
    
    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """清理文件名，移除不安全字符"""
        import re
        # 移除或替换不安全字符
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # 移除连续的空格和点
        filename = re.sub(r'[\s.]+', '_', filename)
        # 限制长度
        if len(filename) > 50:
            filename = filename[:50]
        return filename.strip('_')


def generate_archive_filename(task_names: List[str], lang_out: Optional[str] = None) -> str:
    """
    生成压缩包文件名
    
    Args:
        task_names: 任务名称列表
        lang_out: 输出语言
        
    Returns:
        压缩包文件名（不含扩展名）
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if len(task_names) == 1:
        # 单个文件，使用原文件名
        base_name = Path(task_names[0]).stem
        if lang_out:
            return f"{base_name}_{lang_out}_{timestamp}"
        else:
            return f"{base_name}_{timestamp}"
    else:
        # 多个文件
        if lang_out:
            return f"babeldoc_batch_{lang_out}_{timestamp}"
        else:
            return f"babeldoc_batch_{timestamp}"


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小显示"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    size_float = float(size_bytes)
    while size_float >= 1024 and i < len(size_names) - 1:
        size_float /= 1024.0
        i += 1
    
    return f"{size_float:.1f} {size_names[i]}"