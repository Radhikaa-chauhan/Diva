import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    QUALITY_CHECK = "quality_check"
    COMPLETE = "complete"
    FAILED = "failed"


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    reference_photo_id: Mapped[str] = mapped_column(String(36), ForeignKey("reference_photos.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=JobStatus.PENDING, index=True)
    selfie_image_url: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="jobs")
    reference = relationship("ReferencePhoto", lazy="joined")