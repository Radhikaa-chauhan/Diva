import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Use QueuePool for PostgreSQL (production) and StaticPool for SQLite (dev).
if settings.database_url.startswith("sqlite"):
    logger.info("Using SQLite database with StaticPool")
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    logger.info("Using PostgreSQL database with QueuePool (pool_size=%s, max_overflow=%s)", settings.db_pool_size, settings.db_max_overflow)
    engine = create_engine(
        settings.database_url,
        poolclass=QueuePool,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()