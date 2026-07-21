"""Health check router for monitoring database connectivity and pool metrics."""
import logging

from fastapi import APIRouter

from app.database import check_db_connection, get_pool_status

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Return health status including database connectivity and pool status."""
    db_healthy = check_db_connection(max_retries=1)
    pool_stats = get_pool_status()
    status_str = "ok" if db_healthy else "degraded"

    logger.debug("Health check pinged — status=%s, db=%s", status_str, db_healthy)
    return {
        "status": status_str,
        "database": {
            "healthy": db_healthy,
            "pool": pool_stats,
        },
    }


@router.get("/health/db")
def db_health():
    """Health probe for database pool status"""
    status = get_pool_status()
    return {"status": "healthy", "pool": status}

@router.get("/health/db-connectivity")
def db_connectivity():
    """Quick connectivity check"""
    is_connected = check_db_connection(max_retries=1, retry_delay=0.1)
    return {"connected": is_connected}