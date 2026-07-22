"""Search users and public posts (same ilike pattern as jobs history search)."""
import logging
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_optional
from app.models.user import User
from app.routers.feed import list_posts
from app.schemas import AuthorSummary, PaginatedResponse, PostOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/users", response_model=PaginatedResponse[AuthorSummary])
def search_users(
    q: str = Query(..., min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AuthorSummary]:
    term = f"%{q.strip()}%"
    base = select(User).where(
        User.is_deleted.is_(False),
        User.is_active.is_(True),
        or_(User.username.ilike(term), User.display_name.ilike(term)),
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(desc(User.followers_count)).offset((page - 1) * per_page).limit(per_page)
    ).all()

    return PaginatedResponse(
        items=[AuthorSummary.model_validate(u) for u in rows],
        total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )


@router.get("/posts", response_model=PaginatedResponse[PostOut])
def search_posts(
    q: str = Query(..., min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> PaginatedResponse[PostOut]:
    """Public posts whose caption matches. Reuses the feed listing pipeline."""
    return list_posts(db, current_user, page, per_page, caption_search=q.strip())
