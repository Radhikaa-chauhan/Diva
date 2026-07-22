"""Feed and explore: public posts, chronological (Phase 1 — no ranking yet)."""
import logging
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, exists, func, literal, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_current_user_optional
from app.models.social import Follow, Like, Post, SavedPost
from app.models.user import User
from app.routers.posts import build_post_out
from app.schemas import PaginatedResponse, PostOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feed"])


def list_posts(
    db: Session,
    viewer: User | None,
    page: int,
    per_page: int,
    following_ids: list[str] | None = None,
    include_private_for: str | None = None,
) -> PaginatedResponse[PostOut]:
    """Post listings, newest first. Public-only, except a profile owner viewing
    their own grid (include_private_for). is_liked/is_saved are hydrated as
    correlated EXISTS subqueries in the same statement — no per-row query (no N+1)."""
    from sqlalchemy import or_

    base = select(Post).where(Post.is_deleted.is_(False))
    if include_private_for:
        base = base.where(
            or_(Post.visibility == "public", Post.user_id == include_private_for)
        )
    else:
        base = base.where(Post.visibility == "public")
    if following_ids is not None:
        base = base.where(Post.user_id.in_(following_ids))

    if viewer:
        is_liked_expr = exists(
            select(Like.user_id).where(Like.post_id == Post.id, Like.user_id == viewer.id)
        )
        is_saved_expr = exists(
            select(SavedPost.user_id).where(SavedPost.post_id == Post.id, SavedPost.user_id == viewer.id)
        )
    else:
        is_liked_expr = literal(False)
        is_saved_expr = literal(False)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    stmt = (
        base.add_columns(is_liked_expr.label("is_liked"), is_saved_expr.label("is_saved"))
        .order_by(desc(Post.created_at), desc(Post.id))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = db.execute(stmt).all()

    items = [build_post_out(post, bool(is_liked), bool(is_saved)) for post, is_liked, is_saved in rows]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )


@router.get("/api/feed", response_model=PaginatedResponse[PostOut])
def get_feed(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[PostOut]:
    """Posts from users you follow. Falls back to explore if you follow no one."""
    following_ids = list(
        db.scalars(select(Follow.following_id).where(Follow.follower_id == current_user.id)).all()
    )
    if not following_ids:
        return list_posts(db, current_user, page, per_page)
    return list_posts(db, current_user, page, per_page, following_ids=following_ids)


@router.get("/api/explore", response_model=PaginatedResponse[PostOut])
def get_explore(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> PaginatedResponse[PostOut]:
    """All public posts, newest first. Works with or without auth."""
    return list_posts(db, current_user, page, per_page)
