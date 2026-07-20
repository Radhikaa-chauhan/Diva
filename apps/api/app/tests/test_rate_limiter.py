"""Unit tests for SlidingWindowRateLimiter and rate_limiter service."""
import asyncio
import time
import unittest
from fastapi import HTTPException

from app.services.rate_limiter import (
    RateLimitConfig,
    RateLimitStatus,
    SlidingWindowRateLimiter,
)


class TestRateLimiter(unittest.TestCase):

    def test_config_validation(self):
        """Verify RateLimitConfig raises ValueError on invalid parameters."""
        config = RateLimitConfig(max_requests=5, window_seconds=60)
        self.assertEqual(config.max_requests, 5)

        with self.assertRaises(ValueError):
            RateLimitConfig(max_requests=0, window_seconds=60)

        with self.assertRaises(ValueError):
            RateLimitConfig(max_requests=5, window_seconds=0)

        with self.assertRaises(ValueError):
            RateLimitConfig(max_requests=5, window_seconds=60, exponential_backoff_base=0.5)

        with self.assertRaises(ValueError):
            RateLimitConfig(max_requests=5, window_seconds=60, max_backoff_multiplier=-1)

        with self.assertRaises(ValueError):
            RateLimitConfig(max_requests=5, window_seconds=60, jitter_seconds=(5, 2))  # type: ignore

    def test_basic_rate_limiting(self):
        """Verify sliding window rate limiting behavior."""
        config = RateLimitConfig(
            max_requests=3,
            window_seconds=10,
            jitter_seconds=(0, 0),
        )
        limiter = SlidingWindowRateLimiter(config)
        ip = "192.168.1.1"

        for _ in range(3):
            status, _ = limiter.is_allowed(ip)
            self.assertIn(status, (RateLimitStatus.ALLOWED, RateLimitStatus.WARNED))

        status, retry_after = limiter.is_allowed(ip)
        self.assertEqual(status, RateLimitStatus.BLOCKED)
        self.assertGreaterEqual(retry_after, 10)

    def test_admin_vip_whitelisting(self):
        """Verify VIP users bypass rate limits and admins can perform manual resets."""
        config = RateLimitConfig(
            max_requests=1,
            window_seconds=10,
            vip_user_ids={"vip_user_123"},
            admin_user_ids={"admin_user_456"},
        )
        limiter = SlidingWindowRateLimiter(config)
        ip = "192.168.1.2"

        status, _ = limiter.is_allowed(ip)
        self.assertEqual(status, RateLimitStatus.ALLOWED)

        status, _ = limiter.is_allowed(ip)
        self.assertEqual(status, RateLimitStatus.BLOCKED)

        status, _ = limiter.is_allowed(ip, user_id="vip_user_123")
        self.assertEqual(status, RateLimitStatus.ALLOWED)

    def test_reset_authorization(self):
        """Verify reset authorization rules."""
        config = RateLimitConfig(
            max_requests=1,
            window_seconds=10,
            admin_user_ids={"admin_1"},
            vip_user_ids={"vip_1"},
        )
        limiter = SlidingWindowRateLimiter(config)
        ip = "192.168.1.3"

        limiter.is_allowed(ip)
        status, _ = limiter.is_allowed(ip)
        self.assertEqual(status, RateLimitStatus.BLOCKED)

        # Unauthorized reset (manual with non-admin user)
        with self.assertRaises(HTTPException) as ctx:
            limiter.reset(ip, reason="manual", user_id="regular_user")
        self.assertEqual(ctx.exception.status_code, 403)

        # Authorized reset: system / successful_login
        limiter.reset(ip, reason="successful_login")
        status, _ = limiter.is_allowed(ip)
        self.assertEqual(status, RateLimitStatus.ALLOWED)

        limiter.is_allowed(ip)

        # Authorized reset: admin user
        limiter.reset(ip, reason="manual", user_id="admin_1")
        status, _ = limiter.is_allowed(ip)
        self.assertEqual(status, RateLimitStatus.ALLOWED)

    def test_exponential_backoff_calculation(self):
        """Verify backoff multiplier increases with violations up to max cap."""
        config = RateLimitConfig(
            max_requests=1,
            window_seconds=10,
            exponential_backoff_base=2.0,
            max_backoff_multiplier=3,
            jitter_seconds=(0, 0),
        )
        limiter = SlidingWindowRateLimiter(config)
        ip = "192.168.1.4"

        limiter.is_allowed(ip)

        status1, retry1 = limiter.is_allowed(ip)
        self.assertEqual(status1, RateLimitStatus.BLOCKED)
        self.assertTrue(9 <= retry1 <= 11)

        status2, retry2 = limiter.is_allowed(ip)
        self.assertEqual(status2, RateLimitStatus.BLOCKED)
        self.assertTrue(19 <= retry2 <= 21)

        status3, retry3 = limiter.is_allowed(ip)
        self.assertEqual(status3, RateLimitStatus.BLOCKED)
        self.assertTrue(39 <= retry3 <= 41)

    def test_violation_decay(self):
        """Verify violation count decays after decay period."""
        config = RateLimitConfig(
            max_requests=1,
            window_seconds=10,
            violation_decay_seconds=1,
            jitter_seconds=(0, 0),
        )
        limiter = SlidingWindowRateLimiter(config)
        ip = "192.168.1.5"

        limiter.is_allowed(ip)
        limiter.is_allowed(ip)
        self.assertEqual(limiter._violations[ip], 1)

        time.sleep(1.1)

        limiter._apply_violation_decay(ip, time.monotonic())
        self.assertEqual(limiter._violations.get(ip, 0), 0)

    def test_cleanup_old_entries(self):
        """Verify cleanup_old_entries removes expired IP records."""
        config = RateLimitConfig(
            max_requests=5,
            window_seconds=1,
            violation_decay_seconds=1,
        )
        limiter = SlidingWindowRateLimiter(config)
        ip = "192.168.1.6"

        limiter.is_allowed(ip)
        self.assertIn(ip, limiter._requests)

        time.sleep(1.1)
        cleaned = limiter.cleanup_old_entries()
        self.assertEqual(cleaned, 1)
        self.assertNotIn(ip, limiter._requests)

    def test_auto_cleanup_task(self):
        """Verify auto-starting cleanup task."""
        async def run_async_test():
            config = RateLimitConfig(
                max_requests=5,
                window_seconds=1,
                cleanup_interval_seconds=1,
            )
            limiter = SlidingWindowRateLimiter(config)

            task = limiter.start_cleanup_task()
            self.assertIsNotNone(task)
            self.assertFalse(task.done())
            task.cancel()

        asyncio.run(run_async_test())


if __name__ == "__main__":
    unittest.main()
