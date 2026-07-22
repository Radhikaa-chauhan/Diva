"""Follow/unfollow and followers/following listings."""
import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_current_user_optional
from app.models.social import Follow, Post
from app.models.user import User
from app.schemas import AuthorSummary, FollowStatusOut, PaginatedResponse, PostOut, ProfileOut
from app.services.stats_cache import stats_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


def _get_target_user(user_id: str, db: Session) -> User:
    target = db.get(User, user_id)
    if target is None or target.is_deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return target


def _get_user_by_username(username: str, db: Session) -> User:
    target = db.scalars(select(User).where(User.username == username)).first()
    if target is None or target.is_deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return target


@router.get("/by-username/{username}", response_model=ProfileOut)
def get_profile(
    username: str,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> ProfileOut:
    """Public profile: counts, is_following state for the viewer."""
    target = _get_user_by_username(username, db)

    posts_count = db.scalar(
        select(func.count()).select_from(Post).where(
            Post.user_id == target.id,
            Post.is_deleted.is_(False),
            Post.visibility == "public",
        )
    ) or 0

    is_following = (
        current_user is not None
        and db.get(Follow, (current_user.id, target.id)) is not None
    )

    return ProfileOut(
        id=target.id,
        username=target.username,
        display_name=target.display_name,
        avatar_url=target.avatar_url,
        bio=target.bio,
        followers_count=target.followers_count,
        following_count=target.following_count,
        posts_count=posts_count,
        is_following=is_following,
        created_at=target.created_at,
    )


@router.get("/by-username/{username}/posts", response_model=PaginatedResponse[PostOut])
def get_profile_posts(
    username: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> PaginatedResponse[PostOut]:
    """A user's post grid: public to everyone, private included for the owner."""
    from app.routers.feed import list_posts

    target = _get_user_by_username(username, db)
    is_owner = current_user is not None and current_user.id == target.id
    return list_posts(
        db,
        current_user,
        page,
        per_page,
        following_ids=[target.id],
        include_private_for=target.id if is_owner else None,
    )


@router.post("/{user_id}/follow", response_model=FollowStatusOut)
def follow_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FollowStatusOut:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    target = _get_target_user(user_id, db)
    existing = db.get(Follow, (current_user.id, target.id))
    if existing is None:
        db.add(Follow(follower_id=current_user.id, following_id=target.id))
        target.followers_count += 1
        current_user.following_count += 1
        db.commit()
        stats_cache.invalidate(current_user.id)
        logger.info("User %s followed %s", current_user.id, target.id)
    # Idempotent: already following is not an error.

    return FollowStatusOut(is_following=True, followers_count=target.followers_count)


@router.delete("/{user_id}/follow", response_model=FollowStatusOut)
def unfollow_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FollowStatusOut:
    target = _get_target_user(user_id, db)
    existing = db.get(Follow, (current_user.id, target.id))
    if existing is not None:
        db.delete(existing)
        target.followers_count = max(0, target.followers_count - 1)
        current_user.following_count = max(0, current_user.following_count - 1)
        db.commit()
        stats_cache.invalidate(current_user.id)
        logger.info("User %s unfollowed %s", current_user.id, target.id)
    # Idempotent: not following is not an error.

    return FollowStatusOut(is_following=False, followers_count=target.followers_count)


@router.get("/{user_id}/followers", response_model=PaginatedResponse[AuthorSummary])
def list_followers(
    user_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AuthorSummary]:
    _get_target_user(user_id, db)

    base = (
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.following_id == user_id, User.is_deleted.is_(False))
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(Follow.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    ).all()

    return PaginatedResponse(
        items=[AuthorSummary.model_validate(u) for u in rows],
        total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )


@router.get("/{user_id}/following", response_model=PaginatedResponse[AuthorSummary])
def list_following(
    user_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AuthorSummary]:
    _get_target_user(user_id, db)

    base = (
        select(User)
        .join(Follow, Follow.following_id == User.id)
        .where(Follow.follower_id == user_id, User.is_deleted.is_(False))
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(Follow.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    ).all()

    return PaginatedResponse(
        items=[AuthorSummary.model_validate(u) for u in rows],
        total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )

