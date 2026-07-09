import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReferencePhoto(Base):
    __tablename__ = "reference_photos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String, nullable=False)
    collection: Mapped[str | None] = mapped_column(String, nullable=True)
    thumbnail_url: Mapped[str] = mapped_column(Text, nullable=False)
    style_description: Mapped[dict] = mapped_column(JSON, nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())