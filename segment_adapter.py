"""Adapter layer to use segmented DB cache with existing code.

Wraps segmented cache to provide same interface as local_intel_db.
Automatically selects segments based on query date range.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from db_segment_cache import SegmentedDBCache


_segment_cache: Optional[SegmentedDBCache] = None
_local_cache: Optional[SegmentedDBCache] = None


def init_segment_cache(max_cache_mb: int = 500) -> SegmentedDBCache:
    """Initialize the segmented cache."""
    global _segment_cache
    _segment_cache = SegmentedDBCache(max_cache_mb=max_cache_mb)
    return _segment_cache


def get_segment_cache() -> Optional[SegmentedDBCache]:
    """Get the global segment cache instance."""
    return _segment_cache


def query_by_date_range(query: str, date_from: datetime, date_to: datetime,
                       params: tuple = ()) -> list[sqlite3.Row]:
    """Query across multiple segments within a date range.
    
    Automatically loads segments, executes query on each, and aggregates results.
    """
    if not _segment_cache:
        return []
    
    results = []
    current_date = date_from.date()
    
    while current_date <= date_to.date():
        segment_name = _segment_cache._get_segment_name(current_date)
        conn = _segment_cache.load_segment(segment_name)
        
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(query, params)
                results.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass  # Segment might not have this table
        
        current_date += timedelta(days=1)
    
    return results


def get_kill_count_segmented(character_id: int, days_back: int = 40) -> int:
    """Get kill count from segmented cache."""
    date_from = datetime.now(timezone.utc) - timedelta(days=days_back)
    date_to = datetime.now(timezone.utc)
    
    results = query_by_date_range(
        """
        SELECT COUNT(DISTINCT ka.killmail_id) AS count
        FROM killmail_attackers ka
        JOIN killmails k ON ka.killmail_id = k.killmail_id
        WHERE ka.attacker_character_id = ? AND k.killmail_time >= ? AND k.killmail_time <= ?
        """,
        date_from,
        date_to,
        (int(character_id), date_from.isoformat(), date_to.isoformat()),
    )
    
    if results:
        return int(results[0][0] or 0)
    return 0


def get_recent_kills_segmented(character_id: int, limit: int = 10, 
                               days_back: int = 40) -> list[sqlite3.Row]:
    """Get recent kills from segmented cache."""
    date_from = datetime.now(timezone.utc) - timedelta(days=days_back)
    date_to = datetime.now(timezone.utc)
    
    results = query_by_date_range(
        """
        SELECT 
            k.killmail_id,
            k.killmail_time,
            k.victim_character_id,
            k.victim_ship_type_id,
            k.solar_system_id
        FROM killmails k
        JOIN killmail_attackers ka ON k.killmail_id = ka.killmail_id
        WHERE ka.attacker_character_id = ? AND k.killmail_time >= ? AND k.killmail_time <= ?
        ORDER BY k.killmail_time DESC
        LIMIT ?
        """,
        date_from,
        date_to,
        (int(character_id), date_from.isoformat(), date_to.isoformat(), limit),
    )
    
    return results[:limit]  # Limit results since we're aggregating from multiple segments


def print_cache_stats():
    """Print segment cache statistics."""
    if _segment_cache:
        stats = _segment_cache.get_cache_stats()
        print(f"\n[CACHE] Segments in memory: {stats['segments_in_memory']}")
        print(f"[CACHE] Cache size: {stats['cache_size_mb']:.1f}MB / {stats['max_cache_mb']:.1f}MB")
        print(f"[CACHE] Total segments on disk: {stats['segments_on_disk']}")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from local_intel_updater import DB_PATH
    
    cache = init_segment_cache(max_cache_mb=500)
    print(f"[SEGMENT] Migrating {DB_PATH} to segmented format...")
    
    from db_segment_cache import migrate_to_segments
    migrate_to_segments(DB_PATH, cache)
    
    print_cache_stats()
