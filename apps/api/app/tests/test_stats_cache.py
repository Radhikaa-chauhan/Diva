"""Unit tests for DashboardStatsCache service."""
import asyncio
import time
import unittest
from unittest.mock import MagicMock

from app.schemas import DashboardStatsOut
from app.services.stats_cache import DashboardStatsCache


class TestDashboardStatsCache(unittest.TestCase):

    def test_constructor_validation(self):
        """Verify constructor parameters are validated."""
        cache = DashboardStatsCache(ttl_seconds=10, cleanup_interval_seconds=60)
        self.assertEqual(cache.ttl_seconds, 10)

        with self.assertRaises(ValueError):
            DashboardStatsCache(ttl_seconds=0)

        with self.assertRaises(ValueError):
            DashboardStatsCache(cleanup_interval_seconds=0)

    def test_monotonic_time_and_hit_miss(self):
        """Verify cache hit and miss behavior using monotonic time."""
        cache = DashboardStatsCache(ttl_seconds=10)
        user = MagicMock()
        user.id = "user_1"
        user.storage_used_bytes = 1048576  # 1 MB

        db = MagicMock()
        mock_row = MagicMock()
        mock_row.total = 10
        mock_row.completed = 8
        mock_row.favorites = 2
        db.execute.return_value.first.return_value = mock_row

        # First call: cache miss, computes from DB
        stats1 = cache.get_stats(db, user)
        self.assertEqual(stats1.total_generations, 10)
        self.assertEqual(stats1.completed_generations, 8)
        self.assertEqual(stats1.favorites_count, 2)
        self.assertEqual(stats1.storage_used_mb, 1.0)
        self.assertEqual(db.execute.call_count, 1)

        # Second call: cache hit, DB not queried again
        stats2 = cache.get_stats(db, user)
        self.assertEqual(stats2.total_generations, 10)
        self.assertEqual(db.execute.call_count, 1)

    def test_first_returns_none(self):
        """Verify .first() returning None handles defaults safely."""
        cache = DashboardStatsCache(ttl_seconds=10)
        user = MagicMock()
        user.id = "user_none"
        user.storage_used_bytes = 0

        db = MagicMock()
        db.execute.return_value.first.return_value = None

        stats = cache.get_stats(db, user)
        self.assertEqual(stats.total_generations, 0)
        self.assertEqual(stats.completed_generations, 0)
        self.assertEqual(stats.favorites_count, 0)

    def test_invalidation(self):
        """Verify invalidation removes item from cache."""
        cache = DashboardStatsCache(ttl_seconds=10)
        user = MagicMock()
        user.id = "user_2"
        user.storage_used_bytes = 0

        db = MagicMock()
        mock_row = MagicMock()
        mock_row.total = 5
        mock_row.completed = 5
        mock_row.favorites = 1
        db.execute.return_value.first.return_value = mock_row

        cache.get_stats(db, user)
        self.assertEqual(db.execute.call_count, 1)

        # Invalidate cache
        cache.invalidate("user_2")

        # Next call computes from DB again
        cache.get_stats(db, user)
        self.assertEqual(db.execute.call_count, 2)

    def test_cleanup_expired(self):
        """Verify cleanup_expired purges entries older than TTL."""
        cache = DashboardStatsCache(ttl_seconds=1)
        user = MagicMock()
        user.id = "user_3"
        user.storage_used_bytes = 0

        db = MagicMock()
        mock_row = MagicMock()
        mock_row.total = 1
        mock_row.completed = 1
        mock_row.favorites = 0
        db.execute.return_value.first.return_value = mock_row

        cache.get_stats(db, user)
        self.assertIn("user_3", cache._cache)

        time.sleep(1.1)

        cleaned = cache.cleanup_expired()
        self.assertEqual(cleaned, 1)
        self.assertNotIn("user_3", cache._cache)

    def test_task_start_and_shutdown(self):
        """Verify background task start and graceful shutdown."""
        async def test_async():
            cache = DashboardStatsCache(ttl_seconds=1, cleanup_interval_seconds=1)
            task = cache.start_cleanup_task()
            self.assertIsNotNone(task)
            self.assertFalse(task.done())

            await cache.stop_cleanup_task()
            self.assertIsNone(cache._cleanup_task)

        asyncio.run(test_async())

    def test_exception_fallback(self):
        """Verify graceful fallback on DB exception."""
        cache = DashboardStatsCache(ttl_seconds=10)
        user = MagicMock()
        user.id = "user_4"

        db = MagicMock()
        db.execute.side_effect = Exception("DB Connection Lost")

        # Returns zeroed default stats instead of crashing
        stats = cache.get_stats(db, user)
        self.assertEqual(stats.total_generations, 0)
        self.assertEqual(stats.completed_generations, 0)
        self.assertEqual(stats.favorites_count, 0)
        self.assertEqual(stats.storage_used_mb, 0.0)


if __name__ == "__main__":
    unittest.main()
