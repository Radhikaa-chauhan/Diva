"""Diva API application entry point.
# Updated environment and auth schema settings

Configures:
- Async lifespan lifecycle for database connectivity checks, auto-migrations, and background task management
- CORS middleware with support for multiple allowed origins
- Static file serving for stored images
- Structured logging and observability
- Graceful shutdown for database connection pool and background tasks
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, check_db_connection, engine, run_auto_migrations
from app.routers import admin, auth, dashboard, engagement, feed, health, jobs, posts, references, search, users
from app.services.rate_limiter import cleanup_rate_limiters
from app.services.stats_cache import stats_cache

# ── Centralized Logging Configuration ────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Safely load application settings
try:
    settings = get_settings()
except Exception as exc:
    logger.critical("Fatal: Failed to load application settings: %s", exc)
    sys.exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and graceful shutdown."""
    logger.info("Initializing Diva API v1.0.0 background services...")

    # 1. Database connectivity check and auto-migrations (inside lifespan, not at module import level)
    try:
        logger.info("Verifying database connectivity...")
        if not check_db_connection():
            logger.error("Database connection check failed — proceeding with startup degraded mode")

        logger.info("Ensuring database tables exist and running auto-migrations...")
        Base.metadata.create_all(bind=engine)
        run_auto_migrations()
    except Exception as exc:
        logger.exception("Error during database startup initialization: %s", exc)

    # 2. Start background tasks (Stats Cache & Rate Limiter cleanup)
    rate_limiter_task = None
    try:
        logger.info("Starting stats cache background cleanup task...")
        stats_cache.start_cleanup_task()

        logger.info("Starting rate limiter background cleanup task...")
        rate_limiter_task = asyncio.create_task(cleanup_rate_limiters())
    except Exception as exc:
        logger.error("Failed to start background cleanup tasks: %s", exc)

    logger.info("Diva API v1.0.0 startup completed — accepting requests")
    yield

    # 3. Graceful Shutdown
    logger.info("Initiating Diva API graceful shutdown sequence...")

    # Cancel rate limiter cleanup task
    if rate_limiter_task and not rate_limiter_task.done():
        rate_limiter_task.cancel()
        try:
            await rate_limiter_task
        except asyncio.CancelledError:
            pass
        logger.info("Rate limiter cleanup task stopped")

    # Stop stats cache cleanup task
    try:
        await stats_cache.stop_cleanup_task()
    except Exception as exc:
        logger.error("Error stopping stats cache task: %s", exc)

    # Dispose DB engine connection pool
    try:
        engine.dispose()
        logger.info("Database engine connection pool disposed")
    except Exception as exc:
        logger.error("Error disposing database engine: %s", exc)

    logger.info("Diva API shutdown completed successfully")


# Initialize FastAPI application
is_debug = getattr(settings, "environment", "production") in ("development", "test", "local")
app = FastAPI(
    title="Diva API",
    version="1.0.0",
    debug=is_debug,
    lifespan=lifespan,
)

# Configure CORS Middleware
dev_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
cors_origins = list(set(settings.allowed_origins_list + dev_origins))
logger.info("Configuring CORS for allowed origins=%s", cors_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Validate and Mount Static Storage Directory
try:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Mounting static storage at /storage from path=%s", settings.storage_dir)
    app.mount("/storage", StaticFiles(directory=settings.storage_dir), name="storage")
except Exception as exc:
    logger.error("Failed to mount static storage directory: %s", exc)

# Mount API Routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(references.router)
app.include_router(jobs.router)
app.include_router(posts.router)
app.include_router(users.router)
app.include_router(feed.router)
app.include_router(engagement.router)
app.include_router(search.router)
app.include_router(admin.router)
app.include_router(dashboard.router)

logger.info("Diva API v1.0.0 configured — all routers mounted")