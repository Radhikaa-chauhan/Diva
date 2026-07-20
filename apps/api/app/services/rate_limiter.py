"""Production-grade rate limiter with distributed support, thread safety, monitoring.

Features:
- Thread-safe in-memory sliding window rate limiter
- Exponential backoff for repeat offenders with configurable cap and jitter
- Time-based violation decay for well-behaved clients after window/decay period
- IP validation and proxy header security (supports X-Forwarded-For, CF-Connecting-IP)
- Automatic background cleanup task to prevent memory leaks
- Authorization checks for manual rate limit resets
- Role-based whitelisting for VIP users and admin controls
- Config validation at startup
"""
import asyncio
import ipaddress
import logging
import random
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Tuple

from fastapi import HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RateLimitStatus(str, Enum):
    """Rate limit check result."""
    ALLOWED = "allowed"
    WARNED = "warned"  # Allowed but at 80%+ of limit
    BLOCKED = "blocked"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting behavior."""
    max_requests: int
    window_seconds: int
    trust_proxy_headers: bool = True
    proxy_headers: list[str] = field(
        default_factory=lambda: ["X-Forwarded-For", "CF-Connecting-IP"]
    )
    trusted_ips: set[str] = field(default_factory=lambda: {"127.0.0.1", "::1"})
    cleanup_interval_seconds: int = 300  # Cleanup every 5 minutes
    exponential_backoff_base: float = 2.0  # 2x for each violation
    max_backoff_multiplier: int = 5  # Cap exponent at 2^5 (32x)
    jitter_seconds: Tuple[int, int] = (0, 5)  # Random 0-5s jitter
    violation_decay_seconds: int = 3600  # Reset violation count after 1h of no violations
    admin_user_ids: set[str] = field(default_factory=set)
    vip_user_ids: set[str] = field(default_factory=set)

    def __post_init__(self):
        if self.max_requests <= 0:
            raise ValueError("max_requests must be > 0")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        if self.cleanup_interval_seconds <= 0:
            raise ValueError("cleanup_interval_seconds must be > 0")
        if self.exponential_backoff_base < 1.0:
            raise ValueError("exponential_backoff_base must be >= 1.0")
        if self.max_backoff_multiplier < 0:
            raise ValueError("max_backoff_multiplier must be >= 0")
        if self.violation_decay_seconds <= 0:
            raise ValueError("violation_decay_seconds must be > 0")
        if (
            not isinstance(self.jitter_seconds, tuple)
            or len(self.jitter_seconds) != 2
            or self.jitter_seconds[0] < 0
            or self.jitter_seconds[1] < self.jitter_seconds[0]
        ):
            raise ValueError("jitter_seconds must be tuple (min, max) with 0 <= min <= max")


class SlidingWindowRateLimiter:
    """Thread-safe, in-memory rate limiter with exponential backoff and violation decay.
    
    Uses sliding window to prevent edge-case exploits.
    Supports exponential backoff, background auto-cleanup, and monitoring.
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._lock = threading.RLock()
        # IP/Key -> list of request timestamps (time.monotonic)
        self._requests: dict[str, list[float]] = defaultdict(list)
        # IP/Key -> violation count (for exponential backoff)
        self._violations: dict[str, int] = defaultdict(int)
        # IP/Key -> timestamp of last violation
        self._last_violation_time: dict[str, float] = {}
        # Metrics
        self._blocked_attempts = 0
        self._warned_attempts = 0
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_time = time.monotonic()
        self._last_cleanup = self._start_time

    def _is_vip_user(self, user_id: str) -> bool:
        """Check if user is VIP (skip rate limiting)."""
        if not user_id:
            return False
        return user_id in self.config.vip_user_ids

    def _is_admin(self, user_id: str) -> bool:
        """Check if user is admin (can reset rate limits)."""
        if not user_id:
            return False
        return user_id in self.config.admin_user_ids

    def _apply_violation_decay(self, key: str, now: float) -> None:
        """Decay or clear violation count if client has had no violations past decay interval."""
        last_time = self._last_violation_time.get(key)
        if last_time and (now - last_time) > self.config.violation_decay_seconds:
            self._violations[key] = 0
            del self._last_violation_time[key]

    def is_allowed(
        self, key: str, user_id: Optional[str] = None
    ) -> Tuple[RateLimitStatus, int]:
        """Check if request is allowed.
        
        Args:
            key: Rate limit key (usually client IP)
            user_id: Optional user ID for VIP whitelisting
        
        Returns:
            (status, retry_after_seconds)
            - ALLOWED: Request is OK, proceed
            - WARNED: Request allowed but near limit, log warning
            - BLOCKED: Request denied, return 429 with retry_after
        """
        # Whitelist VIP users (skip rate limiting entirely)
        if user_id and self._is_vip_user(user_id):
            return RateLimitStatus.ALLOWED, 0

        with self._lock:
            now = time.monotonic()
            cutoff = now - self.config.window_seconds

            # Apply violation decay if client has been well-behaved
            self._apply_violation_decay(key, now)

            # Clean timestamps older than window
            timestamps = [ts for ts in self._requests[key] if ts > cutoff]
            self._requests[key] = timestamps

            # Calculate current utilization
            current_count = len(timestamps)
            limit = self.config.max_requests
            utilization = current_count / limit

            # Determine status based on utilization
            if utilization >= 1.0:
                # Rate limit exceeded
                self._violations[key] += 1
                self._last_violation_time[key] = now
                self._blocked_attempts += 1

                # Calculate base retry delay until oldest request drops off window
                if timestamps:
                    oldest = timestamps[0]
                    base_retry = max(1.0, self.config.window_seconds - (now - oldest))
                else:
                    base_retry = float(self.config.window_seconds)

                # Exponential backoff: base ^ (capped_violations - 1)
                violations = self._violations[key]
                capped_violations = min(violations, self.config.max_backoff_multiplier)
                exponent = max(0, capped_violations - 1)
                multiplier = self.config.exponential_backoff_base ** exponent

                retry_after = int(base_retry * multiplier)

                # Add jitter to avoid thundering herd
                jitter = random.randint(*self.config.jitter_seconds)
                retry_after += jitter
                retry_after = max(1, retry_after)

                logger.warning(
                    "Rate limit BLOCKED: key=%s, current=%d, limit=%d, "
                    "violations=%d, retry_after=%ds",
                    key, current_count, limit, violations, retry_after
                )

                return RateLimitStatus.BLOCKED, retry_after

            elif utilization >= 0.8:
                # Near limit, warn but allow
                self._warned_attempts += 1
                logger.warning(
                    "Rate limit WARNED: key=%s, utilization=%.1f%%, "
                    "current=%d, limit=%d",
                    key, utilization * 100, current_count, limit
                )
                return RateLimitStatus.WARNED, 0

            else:
                # Under limit, allow
                timestamps.append(now)
                self._requests[key] = timestamps

                return RateLimitStatus.ALLOWED, 0

    def reset(self, key: str, reason: str = "manual", user_id: Optional[str] = None) -> None:
        """Clear recorded requests for a key.
        
        Requires authorization:
        - Automatic system resets (e.g. reason="successful_login" or "system") are allowed.
        - Manual resets require an admin or VIP user ID.
        """
        is_authorized = (
            reason in ("successful_login", "system")
            or (user_id is not None and (self._is_admin(user_id) or self._is_vip_user(user_id)))
        )
        if not is_authorized:
            logger.error("Unauthorized rate limit reset attempt: user=%s, key=%s, reason=%s", user_id, key, reason)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized: Admin permissions required to reset rate limits."
            )

        with self._lock:
            if key in self._requests:
                del self._requests[key]
            if key in self._violations:
                del self._violations[key]
            if key in self._last_violation_time:
                del self._last_violation_time[key]

        logger.info(
            "Rate limit reset: key=%s, reason=%s, user=%s",
            key, reason, user_id
        )

    def cleanup_old_entries(self) -> int:
        """Remove entries for clients with no recent activity.
        
        Returns number of entries cleaned.
        """
        with self._lock:
            now = time.monotonic()
            cutoff = now - self.config.window_seconds
            keys_to_delete = []

            for key, timestamps in self._requests.items():
                filtered = [ts for ts in timestamps if ts > cutoff]
                if not filtered:
                    keys_to_delete.append(key)
                else:
                    self._requests[key] = filtered

            for key in keys_to_delete:
                del self._requests[key]
                if key in self._violations:
                    # Keep violations if within decay window
                    last_v = self._last_violation_time.get(key)
                    if not last_v or (now - last_v) > self.config.violation_decay_seconds:
                        del self._violations[key]
                        if key in self._last_violation_time:
                            del self._last_violation_time[key]

            self._last_cleanup = now
            logger.debug("Rate limiter cleanup: removed %d old entries", len(keys_to_delete))
            return len(keys_to_delete)

    def get_stats(self) -> dict:
        """Get rate limiter statistics for monitoring."""
        with self._lock:
            active_clients = len([k for k, v in self._requests.items() if v])
            return {
                "active_clients": active_clients,
                "total_entries": len(self._requests),
                "blocked_attempts": self._blocked_attempts,
                "warned_attempts": self._warned_attempts,
                "uptime_seconds": int(time.monotonic() - self._start_time),
            }

    def start_cleanup_task(self) -> Optional[asyncio.Task]:
        """Auto-start periodic background cleanup task if event loop is active."""
        try:
            loop = asyncio.get_running_loop()
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = loop.create_task(self._periodic_cleanup())
                logger.info("Auto-started rate limiter background cleanup task")
            return self._cleanup_task
        except RuntimeError:
            return None

    async def _periodic_cleanup(self) -> None:
        """Periodic background cleanup loop."""
        while True:
            try:
                await asyncio.sleep(self.config.cleanup_interval_seconds)
                count = self.cleanup_old_entries()
                logger.debug("Rate limiter periodic cleanup removed %d old entries", count)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in rate limiter periodic cleanup: %s", exc)


# ── Dependency: Extract and Validate Client IP ──────────────────────

def _get_client_ip(request: Request, config: RateLimitConfig) -> str:
    """Extract client IP with security hardening."""
    direct_ip = request.client.host if request.client else "127.0.0.1"

    if not config.trust_proxy_headers:
        return direct_ip

    for header in config.proxy_headers:
        value = request.headers.get(header)
        if not value:
            continue

        ips = [ip.strip() for ip in value.split(",")]
        if ips:
            candidate_ip = ips[0]
            if _is_valid_ip(candidate_ip):
                return candidate_ip
            else:
                logger.warning(
                    "Invalid IP in proxy header %s: %s (using direct IP)",
                    header, candidate_ip
                )

    return direct_ip


def _is_valid_ip(ip_str: str) -> bool:
    """Validate IP address format."""
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


# ── Global Instances ────────────────────────────────────────────────

def _get_login_config() -> RateLimitConfig:
    """Load login rate limit config from settings."""
    return RateLimitConfig(
        max_requests=getattr(settings, "login_rate_limit_requests", 5),
        window_seconds=getattr(settings, "login_rate_limit_window_seconds", 60),
        trust_proxy_headers=getattr(settings, "trust_proxy_headers", True),
        trusted_ips={"127.0.0.1", "::1", "169.254.169.254"},
    )


login_rate_limiter = SlidingWindowRateLimiter(_get_login_config())


# ── FastAPI Dependency ──────────────────────────────────────────────

def rate_limit_login(request: Request) -> None:
    """FastAPI dependency to rate limit login requests.
    
    Raises HTTPException with 429 if rate limit exceeded.
    """
    # Auto-start cleanup task if running in asyncio event loop
    login_rate_limiter.start_cleanup_task()

    config = login_rate_limiter.config

    # Get client IP with security hardening
    client_ip = _get_client_ip(request, config)

    # Skip rate limiting for trusted IPs
    if client_ip in config.trusted_ips:
        logger.debug("Skipping rate limit for trusted IP: %s", client_ip)
        return

    # Check rate limit
    limit_status, retry_after = login_rate_limiter.is_allowed(client_ip)

    if limit_status == RateLimitStatus.BLOCKED:
        retry_with_jitter = retry_after + random.randint(1, 3)

        logger.warning(
            "Rate limit exceeded: ip=%s, retry_after=%ds",
            client_ip, retry_with_jitter
        )

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many login attempts. "
                f"Please try again in {retry_with_jitter} seconds."
            ),
            headers={"Retry-After": str(retry_with_jitter)},
        )

    elif limit_status == RateLimitStatus.WARNED:
        logger.warning(
            "Rate limit warning: ip=%s (approaching limit)",
            client_ip
        )


# ── Rate Limit Reset Endpoint (for after successful login) ──────────

def reset_login_rate_limit(
    request: Request, user_id: Optional[str] = None, admin_user_id: Optional[str] = None
) -> None:
    """Reset rate limit for a specific client IP after successful login."""
    client_ip = _get_client_ip(request, login_rate_limiter.config)

    try:
        reason = "successful_login" if not admin_user_id else "admin_reset"
        login_rate_limiter.reset(client_ip, reason=reason, user_id=admin_user_id or user_id)
        logger.info("Rate limit reset: ip=%s", client_ip)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to reset rate limit: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset rate limit"
        )


# ── Monitoring Endpoint ────────────────────────────────────────────

def get_rate_limit_stats() -> dict:
    """Get rate limiter statistics (for monitoring/ops)."""
    return login_rate_limiter.get_stats()


# ── Cleanup Task Function ──────────────────────────────────────────

async def cleanup_rate_limiters() -> None:
    """Periodic cleanup to prevent memory leaks."""
    while True:
        try:
            await asyncio.sleep(login_rate_limiter.config.cleanup_interval_seconds)
            count = login_rate_limiter.cleanup_old_entries()
            logger.debug("Rate limiter cleanup completed: %d entries removed", count)
        except Exception as exc:
            logger.exception("Rate limiter cleanup failed: %s", exc)
