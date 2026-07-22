"""Publish a completed generation job as a post; read/delete a post."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_current_user_optional
from app.models.generation_job import GenerationJob, JobStatus
from app.models.social import Post
from app.models.user import User
from app.schemas import PostCreate, PostOut
from app.services.stats_cache import stats_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/posts", tags=["posts"])


def build_post_out(post: Post, is_liked: bool, is_saved: bool) -> PostOut:
    """Shared Post -> PostOut mapping. Bulk listings (feed/explore) hydrate
    is_liked/is_saved themselves in one query; this just assembles the schema."""
    return PostOut(
        id=post.id,
        author=post.author,
        reference_photo_id=post.reference_photo_id,
        image_url=post.image_url,
        caption=post.caption,
        visibility=post.visibility,
        likes_count=post.likes_count,
        comments_count=post.comments_count,
        saves_count=post.saves_count,
        is_liked=is_liked,
        is_saved=is_saved,
        created_at=post.created_at,
    )


def get_visible_post(post_id: str, viewer: User | None, db: Session) -> Post:
    """Fetch a post, enforcing visibility: public to anyone, private to its owner only."""
    post = db.get(Post, post_id)
    if post is None or post.is_deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    is_owner = viewer is not None and post.user_id == viewer.id
    if post.visibility == "private" and not is_owner:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


def _to_post_out(post: Post, viewer: User | None, db: Session) -> PostOut:
    """Single-post lookup (get/create) — two point queries are fine here;
    it's one post, not a list."""
    is_liked = False
    is_saved = False
    if viewer:
        from app.models.social import Like, SavedPost

        is_liked = db.get(Like, (viewer.id, post.id)) is not None
        is_saved = db.get(SavedPost, (viewer.id, post.id)) is not None

    return build_post_out(post, is_liked, is_saved)


@router.post("", response_model=PostOut, status_code=201)
def create_post(
    body: PostCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PostOut:
    """Publish a completed, owned generation job as a post."""
    job = db.get(GenerationJob, body.job_id)
    if job is None or job.is_deleted:
        raise HTTPException(status_code=404, detail="Generation job not found")
    if job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to publish this job")
    if job.status != JobStatus.COMPLETE or not job.result_urls:
        raise HTTPException(status_code=400, detail="Job is not a completed generation")

    post = Post(
        user_id=current_user.id,
        job_id=job.id,
        reference_photo_id=job.reference_photo_id,
        image_url=job.result_urls[0],
        caption=body.caption,
        visibility=body.visibility,
    )
    db.add(post)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This job has already been published")
    db.refresh(post)

    logger.info("Post created: post_id=%s, user_id=%s, job_id=%s", post.id, current_user.id, job.id)
    return _to_post_out(post, current_user, db)


@router.get("/{post_id}", response_model=PostOut)
def get_post(
    post_id: str,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> PostOut:
    post = get_visible_post(post_id, current_user, db)
    return _to_post_out(post, current_user, db)


@router.delete("/{post_id}", status_code=204)
def delete_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    post = db.get(Post, post_id)
    if post is None or post.is_deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this post")

    post.is_deleted = True
    post.deleted_at = datetime.now(timezone.utc)
    db.commit()

    stats_cache.invalidate(current_user.id)
    logger.info("Post soft-deleted: post_id=%s, user_id=%s", post_id, current_user.id)
