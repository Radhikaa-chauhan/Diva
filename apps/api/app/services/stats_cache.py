"""In-memory TTL stats caching service with event-driven invalidation.

Prevents expensive full-table COUNT(*) and SUM queries on dashboard page loads for active users.

Features:
- Thread-safe in-memory cache using RLock and double-checked locking
- Concurrent computation guard (keeps lock during calculation to prevent duplicate queries)
- Constructor parameter validation (ttl_seconds, cleanup_interval_seconds)
- Monotonic time tracking (time.monotonic) resistant to clock skew
- Single optimized SQL query with conditional aggregation (func.case) and safe .first() fetching
- Exception safety with fallback to default zeroed metrics or stale cache
- Automatic periodic memory cleanup task (cleanup_expired) with lifecycle start/stop
- Robust invalidation on job/storage updates
"""
import asyncio
import logging
import time
from threading import RLock
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.generation_job import GenerationJob, JobStatus
from app.models.user import User
from app.schemas import DashboardStatsOut

logger = logging.getLogger(__name__)

# Default TTL: 300 seconds (5 minutes)
DEFAULT_STATS_TTL_SECONDS = 300
DEFAULT_CLEANUP_INTERVAL_SECONDS = 600  # Cleanup expired entries every 10 minutes


class DashboardStatsCache:
    """Thread-safe, monotonic-time TTL stats cache for user dashboard metrics."""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_STATS_TTL_SECONDS,
        cleanup_interval_seconds: int = DEFAULT_CLEANUP_INTERVAL_SECONDS,
    ):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if cleanup_interval_seconds <= 0:
            raise ValueError("cleanup_interval_seconds must be > 0")

        self.ttl_seconds = ttl_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._cache: dict[str, tuple[float, DashboardStatsOut]] = {}
        self._lock = RLock()
        self._cleanup_task: Optional[asyncio.Task] = None

    def get_stats(self, db: Session, user: User) -> DashboardStatsOut:
        """Retrieves dashboard stats from cache if fresh, otherwise calculates and caches under lock.
        
        Guarantees thread safety and prevents concurrent calculation stampedes.
        Uses 1 single SQL query with conditional aggregation.
        """
        # Ensure cleanup task is running if within an active event loop
        self.start_cleanup_task()

        if not user or not user.id:
            return DashboardStatsOut(
                total_generations=0,
                completed_generations=0,
                favorites_count=0,
                storage_used_mb=0.0,
            )

        user_id = user.id
        now = time.monotonic()

        with self._lock:
            # 1. Check if fresh in cache
            if user_id in self._cache:
                timestamp, cached_stats = self._cache[user_id]
                if now - timestamp < self.ttl_seconds:
                    logger.debug("Dashboard stats cache HIT for user_id=%s", user_id)
                    return cached_stats

            # 2. Cache miss — compute stats under lock to prevent stampede
            logger.info("Dashboard stats cache MISS for user_id=%s — computing aggregate stats", user_id)

            try:
                # Combined single-query aggregation with safe .first() fetch
                stmt = select(
                    func.count(GenerationJob.id).label("total"),
                    func.count(case((GenerationJob.status == JobStatus.COMPLETE, 1))).label("completed"),
                    func.count(case((GenerationJob.is_favorite.is_(True), 1))).label("favorites"),
                ).where(GenerationJob.user_id == user_id)

                row = db.execute(stmt).first()
                total = (row.total if row else 0) or 0
                completed = (row.completed if row else 0) or 0
                favorites = (row.favorites if row else 0) or 0

                storage_bytes = getattr(user, "storage_used_bytes", 0) or 0
                storage_mb = round(storage_bytes / (1024 * 1024), 2)

                stats = DashboardStatsOut(
                    total_generations=total,
                    completed_generations=completed,
                    favorites_count=favorites,
                    storage_used_mb=storage_mb,
                )

                # Store in cache
                self._cache[user_id] = (now, stats)
                return stats

            except Exception as exc:
                logger.exception("Error computing dashboard stats for user_id=%s: %s", user_id, exc)

                # Fallback to stale cached entry if available
                if user_id in self._cache:
                    logger.warning("Returning stale cached stats for user_id=%s after error", user_id)
                    return self._cache[user_id][1]

                # Return default zeroed stats on failure
                return DashboardStatsOut(
                    total_generations=0,
                    completed_generations=0,
                    favorites_count=0,
                    storage_used_mb=0.0,
                )

    def invalidate(self, user_id: str) -> None:
        """Invalidate cached stats for user (called when jobs are created, finished, favorited, or deleted)."""
        if not user_id:
            return
        with self._lock:
            if user_id in self._cache:
                del self._cache[user_id]
                logger.debug("Invalidated dashboard stats cache for user_id=%s", user_id)

    def cleanup_expired(self) -> int:
        """Remove expired entries from memory to prevent memory leaks."""
        now = time.monotonic()
        with self._lock:
            expired_keys = [
                uid for uid, (ts, _) in self._cache.items()
                if now - ts >= self.ttl_seconds
            ]
            for uid in expired_keys:
                del self._cache[uid]
            if expired_keys:
                logger.debug("Cleaned up %d expired entries from stats cache", len(expired_keys))
            return len(expired_keys)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            logger.info("Cleared entire dashboard stats cache")

    def start_cleanup_task(self) -> Optional[asyncio.Task]:
        """Auto-start periodic background cleanup task if event loop is active."""
        try:
            loop = asyncio.get_running_loop()
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = loop.create_task(self._periodic_cleanup())
                logger.info("Auto-started stats cache background cleanup task")
            return self._cleanup_task
        except RuntimeError:
            return None

    async def stop_cleanup_task(self) -> None:
        """Cancel and clean up the background cleanup task during shutdown."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Stopped stats cache background cleanup task")

    async def _periodic_cleanup(self) -> None:
        """Periodic background cleanup loop."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                count = self.cleanup_expired()
                logger.debug("Stats cache periodic cleanup removed %d expired entries", count)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in stats cache periodic cleanup: %s", exc)


# Global singleton instance
stats_cache = DashboardStatsCache()
