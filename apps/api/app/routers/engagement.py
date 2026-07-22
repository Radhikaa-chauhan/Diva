"""Likes, comments, and saves on posts."""
import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_current_user_optional
from app.models.social import Comment, Like, Post, SavedPost
from app.models.user import User
from app.routers.posts import build_post_out, get_visible_post
from app.schemas import (
    CommentCreate,
    CommentOut,
    LikeStatusOut,
    PaginatedResponse,
    PostOut,
    SaveStatusOut,
)
from app.services.stats_cache import stats_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["engagement"])


# ── Likes ─────────────────────────────────────────────────────────────

@router.post("/api/posts/{post_id}/like", response_model=LikeStatusOut)
def like_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LikeStatusOut:
    post = get_visible_post(post_id, current_user, db)
    existing = db.get(Like, (current_user.id, post.id))
    if existing is None:
        db.add(Like(user_id=current_user.id, post_id=post.id))
        post.likes_count += 1
        db.commit()
    return LikeStatusOut(is_liked=True, likes_count=post.likes_count)


@router.delete("/api/posts/{post_id}/like", response_model=LikeStatusOut)
def unlike_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LikeStatusOut:
    post = get_visible_post(post_id, current_user, db)
    existing = db.get(Like, (current_user.id, post.id))
    if existing is not None:
        db.delete(existing)
        post.likes_count = max(0, post.likes_count - 1)
        db.commit()
    return LikeStatusOut(is_liked=False, likes_count=post.likes_count)


# ── Saves ─────────────────────────────────────────────────────────────

@router.post("/api/posts/{post_id}/save", response_model=SaveStatusOut)
def save_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaveStatusOut:
    post = get_visible_post(post_id, current_user, db)
    existing = db.get(SavedPost, (current_user.id, post.id))
    if existing is None:
        db.add(SavedPost(user_id=current_user.id, post_id=post.id))
        post.saves_count += 1
        db.commit()
    return SaveStatusOut(is_saved=True, saves_count=post.saves_count)


@router.delete("/api/posts/{post_id}/save", response_model=SaveStatusOut)
def unsave_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaveStatusOut:
    post = get_visible_post(post_id, current_user, db)
    existing = db.get(SavedPost, (current_user.id, post.id))
    if existing is not None:
        db.delete(existing)
        post.saves_count = max(0, post.saves_count - 1)
        db.commit()
    return SaveStatusOut(is_saved=False, saves_count=post.saves_count)


@router.get("/api/saved", response_model=PaginatedResponse[PostOut])
def list_saved_posts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[PostOut]:
    base = (
        select(Post)
        .join(SavedPost, SavedPost.post_id == Post.id)
        .where(SavedPost.user_id == current_user.id, Post.is_deleted.is_(False))
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(SavedPost.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    ).all()

    items = [build_post_out(post, is_liked=_is_liked(db, current_user.id, post.id), is_saved=True) for post in rows]
    return PaginatedResponse(
        items=items, total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )


def _is_liked(db: Session, user_id: str, post_id: str) -> bool:
    return db.get(Like, (user_id, post_id)) is not None


# ── Comments ──────────────────────────────────────────────────────────

@router.get("/api/posts/{post_id}/comments", response_model=PaginatedResponse[CommentOut])
def list_comments(
    post_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> PaginatedResponse[CommentOut]:
    post = get_visible_post(post_id, current_user, db)

    base = select(Comment).where(Comment.post_id == post.id, Comment.is_deleted.is_(False))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(Comment.created_at.asc()).offset((page - 1) * per_page).limit(per_page)
    ).all()

    return PaginatedResponse(
        items=[CommentOut.model_validate(c) for c in rows],
        total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )


@router.post("/api/posts/{post_id}/comments", response_model=CommentOut, status_code=201)
def create_comment(
    post_id: str,
    body: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentOut:
    post = get_visible_post(post_id, current_user, db)

    comment = Comment(user_id=current_user.id, post_id=post.id, text=body.text)
    db.add(comment)
    post.comments_count += 1
    db.commit()
    db.refresh(comment)

    logger.info("Comment created: comment_id=%s, post_id=%s, user_id=%s", comment.id, post.id, current_user.id)
    return CommentOut.model_validate(comment)


@router.delete("/api/comments/{comment_id}", status_code=204)
def delete_comment(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    comment = db.get(Comment, comment_id)
    if comment is None or comment.is_deleted:
        raise HTTPException(status_code=404, detail="Comment not found")

    post = db.get(Post, comment.post_id)
    is_comment_author = comment.user_id == current_user.id
    is_post_owner = post is not None and post.user_id == current_user.id
    if not (is_comment_author or is_post_owner):
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")

    comment.is_deleted = True
    if post is not None:
        post.comments_count = max(0, post.comments_count - 1)
    db.commit()

    stats_cache.invalidate(current_user.id)
    logger.info("Comment deleted: comment_id=%s, by_user_id=%s", comment_id, current_user.id)
