"""Share a post directly with followed friends + a received-shares inbox."""
import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.social import Follow, Post, PostShare
from app.models.user import User
from app.routers.posts import build_post_out, get_visible_post
from app.schemas import (
    PaginatedResponse,
    ShareCreate,
    ShareResultOut,
    SharedPostOut,
    UnreadCountOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["shares"])


@router.post("/api/posts/{post_id}/share", response_model=ShareResultOut)
def share_post(
    post_id: str,
    body: ShareCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareResultOut:
    """Send a post to people you follow. Recipients must be users you follow."""
    post = get_visible_post(post_id, current_user, db)

    # Only allow sending to people the sender actually follows.
    following = set(
        db.scalars(
            select(Follow.following_id).where(
                Follow.follower_id == current_user.id,
                Follow.following_id.in_(body.user_ids),
            )
        ).all()
    )
    invalid = [u for u in body.user_ids if u not in following]
    if invalid:
        raise HTTPException(status_code=400, detail="You can only share with people you follow.")

    shared = 0
    for recipient_id in following:
        share = PostShare(post_id=post.id, from_user_id=current_user.id, to_user_id=recipient_id)
        db.add(share)
        try:
            db.commit()
            shared += 1
        except IntegrityError:
            db.rollback()  # already shared this post with this person — skip

    logger.info("Post %s shared by %s with %s recipients", post.id, current_user.id, shared)
    return ShareResultOut(shared_with=shared)


@router.get("/api/shares", response_model=PaginatedResponse[SharedPostOut])
def list_received_shares(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[SharedPostOut]:
    """Inbox: posts other people sent to you, newest first."""
    base = (
        select(PostShare)
        .join(Post, Post.id == PostShare.post_id)
        .where(PostShare.to_user_id == current_user.id, Post.is_deleted.is_(False))
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(PostShare.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    ).unique().all()

    items = [
        SharedPostOut(
            share_id=s.id,
            sender=s.sender,
            post=build_post_out(s.post, is_liked=False, is_saved=False),
            is_read=s.is_read,
            created_at=s.created_at,
        )
        for s in rows
    ]
    return PaginatedResponse(
        items=items, total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )


@router.get("/api/shares/unread-count", response_model=UnreadCountOut)
def unread_share_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadCountOut:
    count = db.scalar(
        select(func.count())
        .select_from(PostShare)
        .where(PostShare.to_user_id == current_user.id, PostShare.is_read.is_(False))
    ) or 0
    return UnreadCountOut(count=count)


@router.post("/api/shares/mark-read", response_model=UnreadCountOut)
def mark_shares_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadCountOut:
    """Mark all received shares as read (called when the inbox is opened)."""
    db.execute(
        update(PostShare)
        .where(PostShare.to_user_id == current_user.id, PostShare.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return UnreadCountOut(count=0)
