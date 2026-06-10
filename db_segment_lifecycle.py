"""Lifecycle management for segmented DB.

Current system (40-day rolling window):
- DAYS_BACK = 40 (retention period)
- Cleanup runs at startup and removes anything older than day 40
- New killmails downloaded/processed for latest days
- OLD system: everything in 1 massive SQLite file

New segmented system:
- Each segment = 1 day
- Segments 1-40: active segments on disk (compressed)
- Segment 0 (today): maybe still downloading
- Segment 41+: auto-deleted from disk (already compressed archive if needed)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import json

from paths import user_data_path
from db_segment_cache import SegmentedDBCache


SEGMENTS_DIR = user_data_path(Path("data") / "segments")
RETENTION_INDEX = SEGMENTS_DIR / "retention.json"
DAYS_BACK = 40


class SegmentRetentionManager:
    """Manage segment lifecycle: create → compress → archive → delete."""
    
    def __init__(self, segments_dir: Path = SEGMENTS_DIR, days_back: int = DAYS_BACK):
        self.segments_dir = segments_dir
        self.retention_index_path = RETENTION_INDEX
        self.days_back = days_back
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        self.retention_index = self._load_retention_index()
    
    def _load_retention_index(self) -> dict:
        """Load retention metadata."""
        if not self.retention_index_path.exists():
            return {}
        try:
            with open(self.retention_index_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_retention_index(self):
        """Save retention metadata."""
        with open(self.retention_index_path, 'w') as f:
            json.dump(self.retention_index, f, indent=2)
    
    def get_retention_window(self) -> tuple[datetime, datetime]:
        """Get the date range that should be retained.
        
        Returns:
            (oldest_date, newest_date) in UTC
        """
        today = datetime.now(timezone.utc)
        oldest = today - timedelta(days=self.days_back - 1)
        return (oldest, today)
    
    def should_retain_segment(self, segment_date: datetime.date) -> bool:
        """Check if a segment should be kept based on retention policy."""
        oldest, newest = self.get_retention_window()
        oldest_date = oldest.date()
        newest_date = newest.date()
        
        return oldest_date <= segment_date <= newest_date
    
    def get_active_segments(self) -> list[str]:
        """List all segments that should currently exist."""
        oldest, newest = self.get_retention_window()
        current = oldest.date()
        segments = []
        
        while current <= newest.date():
            segment_name = f"killmails-{current.strftime('%Y-%m-%d')}"
            segments.append(segment_name)
            current += timedelta(days=1)
        
        return sorted(segments)
    
    def get_segments_to_delete(self) -> list[str]:
        """Find segments that should be archived/deleted (older than retention window)."""
        to_delete = []
        
        # Check all segments on disk
        for segment_file in self.segments_dir.glob("killmails-*.db.zst"):
            # Extract date from filename: killmails-2024-12-15.db.zst
            try:
                date_str = segment_file.stem.replace("killmails-", "").replace(".db", "")
                segment_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                
                if not self.should_retain_segment(segment_date):
                    to_delete.append(segment_file.name)
            except ValueError:
                pass
        
        return sorted(to_delete)
    
    def cleanup_old_segments(self, archive_dir: Optional[Path] = None) -> dict:
        """Delete segments older than retention window.
        
        Optionally moves to archive directory before deleting.
        
        Returns:
            dict with stats: deleted_count, freed_mb, archived_count
        """
        to_delete = self.get_segments_to_delete()
        deleted_count = 0
        archived_count = 0
        freed_mb = 0
        
        for segment_file_name in to_delete:
            segment_path = self.segments_dir / segment_file_name
            
            if not segment_path.exists():
                continue
            
            freed_mb += segment_path.stat().st_size / 1024 / 1024
            
            if archive_dir:
                try:
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    segment_path.rename(archive_dir / segment_file_name)
                    archived_count += 1
                    
                    # Update retention index
                    self.retention_index[segment_file_name] = {
                        'archived_at': datetime.now(timezone.utc).isoformat(),
                        'file_size_mb': segment_path.stat().st_size / 1024 / 1024,
                    }
                except Exception as e:
                    print(f"[RETENTION] Archive failed {segment_file_name}: {e}")
            else:
                try:
                    segment_path.unlink()
                    deleted_count += 1
                except Exception as e:
                    print(f"[RETENTION] Delete failed {segment_file_name}: {e}")
        
        if deleted_count or archived_count:
            self._save_retention_index()
        
        return {
            'deleted_count': deleted_count,
            'archived_count': archived_count,
            'freed_mb': freed_mb,
        }
    
    def ensure_segment_exists(self, date: datetime.date) -> Path:
        """Ensure a segment exists for a given date.
        
        If not on disk, creates empty segment.
        Returns path to segment DB file.
        """
        segment_name = f"killmails-{date.strftime('%Y-%m-%d')}"
        segment_path = self.segments_dir / f"{segment_name}.db"
        
        if segment_path.exists():
            return segment_path
        
        # Create empty segment with schema
        conn = sqlite3.connect(str(segment_path))
        cur = conn.cursor()
        
        # Copy schema
        cur.execute("""
            CREATE TABLE IF NOT EXISTS killmails (
                killmail_id INTEGER PRIMARY KEY,
                killmail_time TEXT NOT NULL,
                victim_character_id INTEGER,
                victim_ship_type_id INTEGER,
                solar_system_id INTEGER
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS killmail_attackers (
                killmail_id INTEGER NOT NULL,
                attacker_character_id INTEGER NOT NULL,
                final_blow INTEGER DEFAULT 0,
                damage_done INTEGER DEFAULT 0,
                PRIMARY KEY (killmail_id, attacker_character_id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cyno_losses (
                character_id INTEGER PRIMARY KEY,
                last_cyno_time TEXT NOT NULL,
                killmail_id INTEGER NOT NULL,
                ship_type_id INTEGER,
                cyno_module_id INTEGER NOT NULL,
                cyno_module_name TEXT NOT NULL
            )
        """)
        
        # Create indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_killmails_time
            ON killmails(killmail_time DESC)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_attackers_character_killmail
            ON killmail_attackers(attacker_character_id, killmail_id)
        """)
        
        conn.commit()
        conn.close()
        
        return segment_path
    
    def report_status(self):
        """Print retention status."""
        active = self.get_active_segments()
        to_delete = self.get_segments_to_delete()
        
        oldest, newest = self.get_retention_window()
        
        print(f"\n[RETENTION] Status Report:")
        print(f"  Retention window: {oldest.date()} → {newest.date()} ({self.days_back} days)")
        print(f"  Active segments (should exist): {len(active)}")
        print(f"  Segments to delete (older than window): {len(to_delete)}")
        
        if to_delete:
            print(f"  Segments to delete: {to_delete[:5]}{'...' if len(to_delete) > 5 else ''}")


def startup_retention_cleanup(segment_cache: SegmentedDBCache,
                              archive_dir: Optional[Path] = None) -> dict:
    """
    Run during app startup to clean up old segments.
    
    Process:
    1. Identify segments older than DAYS_BACK
    2. Optionally archive them
    3. Delete from active segments directory
    4. Update retention index
    """
    manager = SegmentRetentionManager()
    
    print("\n[STARTUP] Cleaning up old segments...")
    result = manager.cleanup_old_segments(archive_dir=archive_dir)
    
    if result['deleted_count'] or result['archived_count']:
        print(f"[STARTUP] Cleaned up: "
              f"deleted={result['deleted_count']}, "
              f"archived={result['archived_count']}, "
              f"freed={result['freed_mb']:.1f}MB")
    
    manager.report_status()
    return result


if __name__ == "__main__":
    manager = SegmentRetentionManager()
    manager.report_status()
