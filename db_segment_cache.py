"""Segmented DB compression with in-memory caching.

Instead of one large SQLite DB, split data into compressed segments by time period.
Load/decompress segments on-demand into memory cache, keeping disk footprint minimal.

Example:
- killmails-2024-12-01.db.zst (300 MB → 80 MB compressed)
- killmails-2024-12-02.db.zst (310 MB → 85 MB compressed)
...keeps only recent/frequently-used segments in memory.
"""

from __future__ import annotations

import sqlite3
import zstandard as zstd
import lz4.frame
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import threading
import json

from paths import user_data_path


SEGMENTS_DIR = user_data_path(Path("data") / "segments")
SEGMENT_INDEX = SEGMENTS_DIR / "index.json"
MAX_CACHE_SIZE_MB = 500  # Max uncompressed data in memory
MAX_SEGMENT_SIZE_DAYS = 1  # One segment per day


class SegmentedDBCache:
    """Manage compressed DB segments with in-memory caching."""
    
    def __init__(self, max_cache_mb: int = MAX_CACHE_SIZE_MB):
        self.segments_dir = SEGMENTS_DIR
        self.index_path = SEGMENT_INDEX
        self.max_cache_bytes = max_cache_mb * 1024 * 1024
        self.cache: dict[str, bytes] = {}  # segment_name -> uncompressed data
        self.cache_size = 0
        self.lock = threading.RLock()
        self.index = self._load_index()
    
    def _load_index(self) -> dict:
        """Load segment metadata index."""
        if not self.index_path.exists():
            return {}
        try:
            with open(self.index_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_index(self):
        """Save segment metadata index."""
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def _get_segment_name(self, date: datetime.date) -> str:
        """Generate segment name for a date: 'killmails-2024-12-01'."""
        return f"killmails-{date.strftime('%Y-%m-%d')}"
    
    def _get_segment_path(self, segment_name: str, compressed: bool = True) -> Path:
        """Get filesystem path for a segment."""
        ext = ".db.zst" if compressed else ".db"
        return self.segments_dir / f"{segment_name}{ext}"
    
    def load_segment(self, segment_name: str) -> Optional[sqlite3.Connection]:
        """Load a segment into memory and return SQLite connection.
        
        If segment is compressed on disk, decompress into memory.
        Cache the uncompressed data for subsequent queries.
        """
        with self.lock:
            # Check if already in memory cache
            if segment_name in self.cache:
                return self._open_memory_db(self.cache[segment_name])
            
            # Load from disk
            compressed_path = self._get_segment_path(segment_name, compressed=True)
            if not compressed_path.exists():
                return None
            
            # Decompress and cache
            uncompressed_data = self._decompress_file(compressed_path)
            if uncompressed_data is None:
                return None
            
            # Cache management: evict oldest if needed
            data_size = len(uncompressed_data)
            while self.cache_size + data_size > self.max_cache_bytes and self.cache:
                oldest_key = min(self.cache.keys())
                self.cache_size -= len(self.cache.pop(oldest_key))
            
            self.cache[segment_name] = uncompressed_data
            self.cache_size += data_size
            
            return self._open_memory_db(uncompressed_data)
    
    @staticmethod
    def _decompress_file(path: Path) -> Optional[bytes]:
        """Decompress a .zst file."""
        try:
            if path.suffix == '.zst':
                with open(path, 'rb') as f:
                    cctx = zstd.ZstdDecompressor()
                    return cctx.decompress(f.read())
            elif path.suffix == '.lz4':
                with open(path, 'rb') as f:
                    return lz4.frame.decompress(f.read())
        except Exception as e:
            print(f"[SEGMENT] Decompress error {path}: {e}")
        return None
    
    @staticmethod
    def _open_memory_db(data: bytes) -> sqlite3.Connection:
        """Open SQLite DB from bytes in memory."""
        conn = sqlite3.connect(':memory:')
        conn.deserialize(data)
        conn.row_factory = sqlite3.Row
        return conn
    
    def compress_and_store(self, segment_name: str, db_path: Path, 
                          compression: str = "zstd") -> bool:
        """Compress a DB segment and store on disk."""
        if not db_path.exists():
            return False
        
        try:
            with open(db_path, 'rb') as f:
                data = f.read()
            
            if compression == "zstd":
                cctx = zstd.ZstdCompressor(level=10)  # Max compression
                compressed = cctx.compress(data)
            elif compression == "lz4":
                compressed = lz4.frame.compress(data, compression_level=12)
            else:
                return False
            
            # Store compressed
            ext = ".db.zst" if compression == "zstd" else ".db.lz4"
            out_path = self.segments_dir / f"{segment_name}{ext}"
            
            with open(out_path, 'wb') as f:
                f.write(compressed)
            
            # Update index
            ratio = len(compressed) / len(data) if data else 0
            self.index[segment_name] = {
                'compressed_size': len(compressed),
                'uncompressed_size': len(data),
                'compression_ratio': ratio,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'compression': compression,
            }
            self._save_index()
            
            print(f"[SEGMENT] {segment_name}: "
                  f"{len(data)/1024/1024:.1f}MB → "
                  f"{len(compressed)/1024/1024:.1f}MB ({ratio*100:.1f}%)")
            
            return True
        
        except Exception as e:
            print(f"[SEGMENT] Compress error {segment_name}: {e}")
            return False
    
    def get_cache_stats(self) -> dict:
        """Return cache usage statistics."""
        with self.lock:
            return {
                'segments_in_memory': len(self.cache),
                'cache_size_mb': self.cache_size / 1024 / 1024,
                'max_cache_mb': self.max_cache_bytes / 1024 / 1024,
                'segments_on_disk': len(self.index),
            }


def migrate_to_segments(source_db: Path, segment_cache: SegmentedDBCache) -> None:
    """Migrate from single large DB to segmented compressed format.
    
    1. Query killmails by date range
    2. Create temporary segment DB for each date
    3. Compress and store each segment
    4. Verify, then delete original DB
    """
    if not source_db.exists():
        print(f"[MIGRATE] Source DB not found: {source_db}")
        return
    
    print(f"[MIGRATE] Starting migration from {source_db}")
    
    conn = sqlite3.connect(str(source_db))
    cur = conn.cursor()
    
    # Find date range
    cur.execute("SELECT MIN(killmail_time), MAX(killmail_time) FROM killmails")
    result = cur.fetchone()
    if not result or not result[0]:
        print("[MIGRATE] No killmail data found")
        conn.close()
        return
    
    min_time_str = result[0]
    max_time_str = result[1]
    
    min_date = datetime.fromisoformat(min_time_str.replace('Z', '+00:00')).date()
    max_date = datetime.fromisoformat(max_time_str.replace('Z', '+00:00')).date()
    
    current_date = min_date
    total_size = 0
    total_compressed = 0
    
    while current_date <= max_date:
        segment_name = segment_cache._get_segment_name(current_date)
        next_date = current_date + timedelta(days=1)
        
        # Create temporary segment DB with data for this date
        temp_segment = segment_cache.segments_dir / f"{segment_name}.tmp.db"
        segment_cache.segments_dir.mkdir(parents=True, exist_ok=True)
        
        segment_conn = sqlite3.connect(str(temp_segment))
        segment_cur = segment_conn.cursor()
        
        # Copy schema
        for row in cur.execute("SELECT sql FROM sqlite_master WHERE type='table'"):
            segment_cur.execute(row[0])
        
        # Copy data for this date range
        time_start = f"{current_date}T00:00:00Z"
        time_end = f"{next_date}T00:00:00Z"
        
        for table in ['killmails', 'killmail_attackers', 'cyno_losses']:
            try:
                segment_cur.execute(
                    f"INSERT INTO {table} SELECT * FROM {table} "
                    f"WHERE killmail_time >= ? AND killmail_time < ?",
                    (time_start, time_end)
                )
            except sqlite3.OperationalError:
                pass
        
        segment_conn.commit()
        segment_conn.close()
        
        # Compress and store
        if segment_cache.compress_and_store(segment_name, temp_segment, compression="zstd"):
            total_size += temp_segment.stat().st_size
            compressed_path = segment_cache._get_segment_path(segment_name)
            total_compressed += compressed_path.stat().st_size
            temp_segment.unlink()
        
        current_date = next_date
    
    conn.close()
    
    print(f"[MIGRATE] Complete: {total_size/1024/1024:.1f}MB → "
          f"{total_compressed/1024/1024:.1f}MB ({total_compressed/total_size*100:.1f}%)")


if __name__ == "__main__":
    cache = SegmentedDBCache()
    print(cache.get_cache_stats())
