"""Social layer models: Post, Follow, Like, Comment, SavedPost.

Conventions match the existing models: String(36) UUID PKs,
timezone-aware server-default timestamps, soft delete via is_deleted.
Engagement counters are denormalized onto Post (updated in the same
transaction as the Like/Comment/SavedPost row) so feed reads never COUNT(*).
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PostVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("idx_posts_visibility_created", "visibility", "created_at"),
        Index("idx_posts_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # One post per generation job — the job supplies the image.
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("generation_jobs.id"), nullable=False, unique=True
    )
    # Style origin: lets any viewer jump into "use this style".
    reference_photo_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("reference_photos.id"), nullable=True
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    visibility: Mapped[str] = mapped_column(String(10), nullable=False, default=PostVisibility.PUBLIC)
    likes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    saves_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    author = relationship("User", lazy="joined")
    reference = relationship("ReferencePhoto", lazy="joined")


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (
        CheckConstraint("follower_id != following_id", name="ck_no_self_follow"),
        Index("idx_follows_following", "following_id"),
    )

    follower_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    following_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Like(Base):
    __tablename__ = "likes"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("posts.id"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (Index("idx_comments_post_created", "post_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    post_id: Mapped[str] = mapped_column(String(36), ForeignKey("posts.id"), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author = relationship("User", lazy="joined")


class SavedPost(Base):
    __tablename__ = "saved_posts"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), primary_key=True, index=True
    )
    post_id: Mapped[str] = mapped_column(String(36), ForeignKey("posts.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PostShare(Base):
    """A post sent directly from one user to a followed user (DM-style share)."""
    __tablename__ = "post_shares"
    __table_args__ = (
        # One row per (sender, recipient, post) — re-sharing the same post is a no-op.
        Index("ux_share_from_to_post", "from_user_id", "to_user_id", "post_id", unique=True),
        Index("idx_shares_recipient_created", "to_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    post_id: Mapped[str] = mapped_column(String(36), ForeignKey("posts.id"), nullable=False)
    from_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sender = relationship("User", foreign_keys=[from_user_id], lazy="joined")
    post = relationship("Post", lazy="joined")
