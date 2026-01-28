"""
Multi-level caching system for the geocoding pipeline.
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
from cachetools import LRUCache
from .config import Config
from .logger import Logger

logger = Logger.get_logger(__name__)


class CacheManager:
    """Multi-level cache with file-based persistence and in-memory LRU cache."""
    
    def __init__(self, cache_dir: Optional[Path] = None, 
                 ttl_hours: Optional[int] = None,
                 max_memory_size: Optional[int] = None):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Directory for file cache
            ttl_hours: Time-to-live in hours
            max_memory_size: Maximum items in memory cache
        """
        self.cache_dir = cache_dir or Config.CACHE_DIR
        self.ttl_hours = ttl_hours or Config.CACHE_TTL_HOURS
        self.max_memory_size = max_memory_size or Config.CACHE_MAX_SIZE
        
        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory LRU cache
        self.memory_cache: LRUCache = LRUCache(maxsize=self.max_memory_size)
        
        # Statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'memory_hits': 0,
            'file_hits': 0
        }
        
        logger.info(f"Cache initialized - Dir: {self.cache_dir}, TTL: {self.ttl_hours}h")
    
    def _generate_key(self, data: Any) -> str:
        """Generate cache key from data."""
        # Convert data to string and hash it
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()
    
    def _get_file_path(self, key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"{key}.json"
    
    def _is_expired(self, timestamp: str) -> bool:
        """Check if cache entry is expired."""
        try:
            cached_time = datetime.fromisoformat(timestamp)
            expiry_time = cached_time + timedelta(hours=self.ttl_hours)
            return datetime.now() > expiry_time
        except (ValueError, TypeError):
            return True
    
    def get(self, key_data: Any) -> Optional[Dict[str, Any]]:
        """
        Get item from cache.
        
        Args:
            key_data: Data to generate cache key from
            
        Returns:
            Cached data or None if not found/expired
        """
        key = self._generate_key(key_data)
        
        # Check memory cache first
        if key in self.memory_cache:
            cached_item = self.memory_cache[key]
            if not self._is_expired(cached_item['timestamp']):
                self.stats['hits'] += 1
                self.stats['memory_hits'] += 1
                logger.debug(f"Cache HIT (memory) - Key: {key[:8]}...")
                return cached_item['data']
            else:
                # Remove expired item
                del self.memory_cache[key]
        
        # Check file cache
        file_path = self._get_file_path(key)
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    cached_item = json.load(f)
                
                if not self._is_expired(cached_item['timestamp']):
                    # Load into memory cache
                    self.memory_cache[key] = cached_item
                    self.stats['hits'] += 1
                    self.stats['file_hits'] += 1
                    logger.debug(f"Cache HIT (file) - Key: {key[:8]}...")
                    return cached_item['data']
                else:
                    # Remove expired file
                    file_path.unlink()
            except (json.JSONDecodeError, KeyError, IOError) as e:
                logger.warning(f"Cache read error for {key[:8]}...: {str(e)}")
                # Remove corrupted cache file
                if file_path.exists():
                    file_path.unlink()
        
        # Cache miss
        self.stats['misses'] += 1
        logger.debug(f"Cache MISS - Key: {key[:8]}...")
        return None
    
    def set(self, key_data: Any, value: Dict[str, Any]) -> None:
        """
        Store item in cache.
        
        Args:
            key_data: Data to generate cache key from
            value: Data to cache
        """
        key = self._generate_key(key_data)
        
        cached_item = {
            'timestamp': datetime.now().isoformat(),
            'data': value
        }
        
        # Store in memory cache
        self.memory_cache[key] = cached_item
        
        # Store in file cache
        file_path = self._get_file_path(key)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(cached_item, f, ensure_ascii=False, indent=2)
            logger.debug(f"Cache SET - Key: {key[:8]}...")
        except IOError as e:
            logger.warning(f"Cache write error for {key[:8]}...: {str(e)}")
    
    def clear(self) -> None:
        """Clear all cache."""
        # Clear memory cache
        self.memory_cache.clear()
        
        # Clear file cache
        for cache_file in self.cache_dir.glob('*.json'):
            try:
                cache_file.unlink()
            except IOError as e:
                logger.warning(f"Failed to delete cache file {cache_file}: {str(e)}")
        
        # Reset statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'memory_hits': 0,
            'file_hits': 0
        }
        
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'total_requests': total_requests,
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate': f"{hit_rate:.1f}%",
            'memory_hits': self.stats['memory_hits'],
            'file_hits': self.stats['file_hits'],
            'memory_cache_size': len(self.memory_cache),
            'file_cache_size': len(list(self.cache_dir.glob('*.json')))
        }
    
    def cleanup_expired(self) -> int:
        """
        Remove expired cache files.
        
        Returns:
            Number of files removed
        """
        removed = 0
        for cache_file in self.cache_dir.glob('*.json'):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_item = json.load(f)
                
                if self._is_expired(cached_item['timestamp']):
                    cache_file.unlink()
                    removed += 1
            except (json.JSONDecodeError, KeyError, IOError):
                # Remove corrupted files
                cache_file.unlink()
                removed += 1
        
        if removed > 0:
            logger.info(f"Cleaned up {removed} expired cache files")
        
        return removed


# Global cache instance
_cache_manager = None


def get_cache_manager() -> CacheManager:
    """Get or create global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
