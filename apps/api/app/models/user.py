import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    # Public handle for /u/{username} profiles. Nullable only for rows that
    # predate the migration backfill; the app always sets it at signup.
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)

    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(String(300), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    generation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    followers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    following_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_used_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )

    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    otp_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship : lazy loaded to avoid N+1 on user queries
    jobs = relationship("GenerationJob", back_populates="user", lazy="dynamic")
