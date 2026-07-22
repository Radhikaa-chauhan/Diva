"""Admin dashboard: platform stats and user listing. Gated by ADMIN_EMAILS."""
import logging
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.generation_job import GenerationJob
from app.models.social import Post
from app.models.user import User
from app.schemas import AdminStatsOut, AdminUserOut, PaginatedResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/stats", response_model=AdminStatsOut)
def get_stats(db: Session = Depends(get_db)) -> AdminStatsOut:
    """Platform-wide usage stats."""
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    def count(stmt) -> int:
        return db.scalar(stmt) or 0

    users = select(func.count()).select_from(User).where(User.is_deleted.is_(False))

    return AdminStatsOut(
        total_users=count(users),
        active_24h=count(users.where(User.last_login_at >= day_ago)),
        active_7d=count(users.where(User.last_login_at >= week_ago)),
        new_users_7d=count(users.where(User.created_at >= week_ago)),
        verified_users=count(users.where(User.is_email_verified.is_(True))),
        total_generations=count(select(func.count()).select_from(GenerationJob).where(GenerationJob.is_deleted.is_(False))),
        total_posts=count(select(func.count()).select_from(Post).where(Post.is_deleted.is_(False))),
    )


@router.get("/users", response_model=PaginatedResponse[AdminUserOut])
def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    q: str | None = Query(None, description="Search email, username, or name"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AdminUserOut]:
    """Paginated user list, newest first."""
    base = select(User).where(User.is_deleted.is_(False))
    if q and q.strip():
        term = f"%{q.strip()}%"
        base = base.where(
            or_(User.email.ilike(term), User.username.ilike(term), User.display_name.ilike(term))
        )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    ).all()

    return PaginatedResponse(
        items=[AdminUserOut.model_validate(u) for u in rows],
        total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )
