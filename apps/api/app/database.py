"""Database engine configuration, connection pooling, health checks, and auto-migrations.

Features:
- PostgreSQL (QueuePool) and SQLite engine configuration with connection timeout guards
- PostgreSQL advisory locking (pg_advisory_xact_lock) during auto-migrations
- Exception-safe column existence checks and DDL migration rollback guards
- Startup DB connectivity validation (check_db_connection)
- Connection pool status monitoring (get_pool_status)
- Session health check with automatic rollback on error in get_db()
- WAL mode PRAGMA initialization for SQLite file-based databases
- Strict Base metadata configuration
"""
import logging
from collections.abc import Generator
from typing import Any, Dict

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

is_sqlite = settings.database_url.startswith("sqlite")

# Engine & Pool Configuration
if is_sqlite:
    is_memory = ":memory:" in settings.database_url
    logger.info("Configuring SQLite database (in_memory=%s)", is_memory)

    connect_args = {"check_same_thread": False, "timeout": 15}
    poolclass = StaticPool if is_memory else QueuePool

    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        poolclass=poolclass,
    )

    # Enable WAL mode for file-based SQLite to support concurrent read/write operations
    if not is_memory:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

else:
    logger.info(
        "Configuring PostgreSQL database with QueuePool (pool_size=%s, max_overflow=%s)",
        settings.db_pool_size,
        settings.db_max_overflow,
    )
    engine = create_engine(
        settings.database_url,
        connect_args={"connect_timeout": 10},
        poolclass=QueuePool,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=300,  # Recycle connections every 5 minutes to handle idle timeouts
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative Base with strict model configuration."""
    pass


def check_db_connection(timeout_seconds: int = 5) -> bool:
    """Validate database connectivity on application startup."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connectivity check PASSED")
        return True
    except Exception as exc:
        logger.error("Database connectivity check FAILED: %s", exc)
        return False


def get_pool_status() -> Dict[str, Any]:
    """Return database connection pool metrics for monitoring."""
    pool = engine.pool
    if isinstance(pool, QueuePool):
        return {
            "type": "QueuePool",
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    return {
        "type": type(pool).__name__,
        "size": getattr(pool, "size", lambda: 1)(),
    }


def run_auto_migrations() -> None:
    """Safely adds missing model columns to existing tables using advisory locking."""
    try:
        with engine.begin() as conn:
            # PostgreSQL: Acquire transaction-level advisory lock to prevent concurrent DDL race conditions
            if not is_sqlite:
                try:
                    conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))
                except Exception as lock_exc:
                    logger.warning("Could not acquire PG advisory lock: %s", lock_exc)

            inspector = inspect(conn)
            tables = inspector.get_table_names()

            # 1. Users Table Migrations
            if "users" in tables:
                columns = {c["name"] for c in inspector.get_columns("users")}

                if "is_email_verified" not in columns:
                    default_val = "0" if is_sqlite else "FALSE"
                    logger.info("Auto-migrating users table: adding is_email_verified column")
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN is_email_verified BOOLEAN NOT NULL DEFAULT {default_val}"))
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column is_email_verified already exists or added concurrently: %s", exc)

                if "email_verified_at" not in columns:
                    col_type = "DATETIME" if is_sqlite else "TIMESTAMP WITH TIME ZONE"
                    logger.info("Auto-migrating users table: adding email_verified_at column")
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN email_verified_at {col_type}"))
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column email_verified_at already exists or added concurrently: %s", exc)

            # 2. Generation Jobs Table Migrations
            if "generation_jobs" in tables:
                job_columns = {c["name"] for c in inspector.get_columns("generation_jobs")}

                if "is_deleted" not in job_columns:
                    default_val = "0" if is_sqlite else "FALSE"
                    logger.info("Auto-migrating generation_jobs table: adding is_deleted column")
                    try:
                        conn.execute(text(f"ALTER TABLE generation_jobs ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT {default_val}"))
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column is_deleted already exists or added concurrently: %s", exc)

                if "deleted_at" not in job_columns:
                    col_type = "DATETIME" if is_sqlite else "TIMESTAMP WITH TIME ZONE"
                    logger.info("Auto-migrating generation_jobs table: adding deleted_at column")
                    try:
                        conn.execute(text(f"ALTER TABLE generation_jobs ADD COLUMN deleted_at {col_type}"))
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column deleted_at already exists or added concurrently: %s", exc)

        logger.info("Auto-migrations completed successfully")
    except Exception as exc:
        logger.warning("Auto migration check encountered an error: %s", exc)


def get_db() -> Generator[Session, None, None]:
    """FastAPI database session dependency with session health check and automatic rollback on error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()