"""Database engine configuration, connection pooling, health checks, and auto-migrations.

Features:
- PostgreSQL (QueuePool) and SQLite engine configuration with connection pre-ping & timeout guards
- Configurable pool recycling (db_pool_recycle_seconds)
- PostgreSQL advisory locking and statement/lock timeouts during auto-migrations
- Schema migration version tracking table (schema_migrations)
- Exponential backoff retry logic for database connection validation (check_db_connection)
- Connection pool status monitoring metrics (get_pool_status)
- Session health check with automatic rollback on error in get_db()
- WAL mode PRAGMA initialization for SQLite file-based databases
- Standardized logging levels across database lifecycle events
"""
import logging
import time
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
pool_recycle_seconds = getattr(settings, "db_pool_recycle_seconds", 300)

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
        pool_pre_ping=True,
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
        "Configuring PostgreSQL database with QueuePool (pool_size=%s, max_overflow=%s, recycle=%ss)",
        settings.db_pool_size,
        settings.db_max_overflow,
        pool_recycle_seconds,
    )
    engine = create_engine(
        settings.database_url,
        connect_args={"connect_timeout": 10},
        poolclass=QueuePool,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=pool_recycle_seconds,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative Base with strict model configuration."""
    pass


def check_db_connection(max_retries: int = 3, retry_delay: float = 1.0) -> bool:
    """Validate database connectivity with exponential backoff retries."""
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connectivity check PASSED (attempt %d/%d)", attempt, max_retries)
            return True
        except (OperationalError, DBAPIError) as exc:
            logger.warning("Database connectivity attempt %d/%d failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(retry_delay * (2 ** (attempt - 1)))
        except Exception as exc:
            logger.error("Unexpected error during DB connectivity check: %s", exc)
            break
    logger.error("Database connectivity check FAILED after %d attempts", max_retries)
    return False


def get_pool_status() -> Dict[str, Any]:
    """Return database connection pool metrics for health probes and monitoring."""
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


def _record_migration(conn, version: str) -> None:
    """Record an applied migration version in schema_migrations."""
    try:
        conn.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:v) ON CONFLICT DO NOTHING"),
            {"v": version},
        )
    except Exception:
        # SQLite fallback for ON CONFLICT
        try:
            conn.execute(text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:v)"), {"v": version})
        except Exception as exc:
            logger.debug("Failed to record migration version %s: %s", version, exc)


def run_auto_migrations() -> None:
    """Safely adds missing model columns to existing tables using advisory locking, timeouts, and version tracking."""
    try:
        with engine.begin() as conn:
            # 1. PostgreSQL: Set lock & statement timeouts and acquire advisory lock
            if not is_sqlite:
                try:
                    conn.execute(text("SET lock_timeout = '10000'"))  # 10s timeout
                    conn.execute(text("SET statement_timeout = '30000'"))  # 30s timeout
                    conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))
                except Exception as lock_exc:
                    logger.warning("Could not set PG migration timeouts or lock: %s", lock_exc)

            # 2. Schema Migration Version Tracking Table
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version VARCHAR(50) PRIMARY KEY, "
                "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))

            inspector = inspect(conn)
            tables = inspector.get_table_names()

            # 3. Users Table Migrations
            if "users" in tables:
                columns = {c["name"] for c in inspector.get_columns("users")}

                if "is_email_verified" not in columns:
                    default_val = "0" if is_sqlite else "FALSE"
                    logger.info("Auto-migrating users table: adding is_email_verified column")
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN is_email_verified BOOLEAN NOT NULL DEFAULT {default_val}"))
                        _record_migration(conn, "v1_user_is_email_verified")
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column is_email_verified already exists or added concurrently: %s", exc)

                if "is_deleted" not in columns:
                    default_val = "0" if is_sqlite else "FALSE"
                    logger.info("Auto-migrating users table: adding is_deleted column")
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT {default_val}"))
                        _record_migration(conn, "v2_user_is_deleted")
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column is_deleted already exists or added concurrently: %s", exc)

                if "token_version" not in columns:
                    logger.info("Auto-migrating users table: adding token_version column")
                    try:
                        conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
                        _record_migration(conn, "v3_user_token_version")
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column token_version already exists or added concurrently: %s", exc)

                if "otp_code" not in columns:
                    logger.info("Auto-migrating users table: adding otp_code column")
                    try:
                        conn.execute(text("ALTER TABLE users ADD COLUMN otp_code VARCHAR(10)"))
                        _record_migration(conn, "v6_user_otp_code")
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column otp_code already exists or added concurrently: %s", exc)

                for col in ("followers_count", "following_count"):
                    if col not in columns:
                        logger.info("Auto-migrating users table: adding %s column", col)
                        try:
                            conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"))
                            _record_migration(conn, f"v8_user_{col}")
                        except (ProgrammingError, OperationalError) as exc:
                            logger.debug("Column %s already exists or added concurrently: %s", col, exc)

                if "otp_expires_at" not in columns:
                    col_type = "DATETIME" if is_sqlite else "TIMESTAMP WITH TIME ZONE"
                    logger.info("Auto-migrating users table: adding otp_expires_at column")
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN otp_expires_at {col_type}"))
                        _record_migration(conn, "v7_user_otp_expires_at")
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column otp_expires_at already exists or added concurrently: %s", exc)

            # 4. Generation Jobs Table Migrations
            if "generation_jobs" in tables:
                job_columns = {c["name"] for c in inspector.get_columns("generation_jobs")}

                if "is_deleted" not in job_columns:
                    default_val = "0" if is_sqlite else "FALSE"
                    logger.info("Auto-migrating generation_jobs table: adding is_deleted column")
                    try:
                        conn.execute(text(f"ALTER TABLE generation_jobs ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT {default_val}"))
                        _record_migration(conn, "v4_jobs_is_deleted")
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column is_deleted already exists or added concurrently: %s", exc)

                if "deleted_at" not in job_columns:
                    col_type = "DATETIME" if is_sqlite else "TIMESTAMP WITH TIME ZONE"
                    logger.info("Auto-migrating generation_jobs table: adding deleted_at column")
                    try:
                        conn.execute(text(f"ALTER TABLE generation_jobs ADD COLUMN deleted_at {col_type}"))
                        _record_migration(conn, "v5_jobs_deleted_at")
                    except (ProgrammingError, OperationalError) as exc:
                        logger.debug("Column deleted_at already exists or added concurrently: %s", exc)

        logger.info("Auto-migrations completed successfully")
    except Exception as exc:
        logger.warning("Auto migration check encountered an error: %s", exc)


def get_db() -> Generator[Session, None, None]:
    """FastAPI database session dependency with pre-flight health check and automatic rollback on error."""
    db = SessionLocal()
    try:
        # Actually test the connection
        db.execute(text("SELECT 1"))
        yield db
    except (DBAPIError, OperationalError) as exc:
        logger.error("Database connection failed in get_db(): %s", exc)
        db.rollback()
        raise
    finally:
        db.close()