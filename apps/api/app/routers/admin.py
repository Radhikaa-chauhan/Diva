"""Admin dashboard: platform stats, user listing, reference management. Gated by ADMIN_EMAILS."""
import io
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from PIL import Image
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.generation_job import GenerationJob
from app.models.reference_photo import ReferencePhoto
from app.models.social import Post
from app.models.user import User
from app.routers.references import clear_references_cache
from app.schemas import (
    AdminStatsOut,
    AdminUserOut,
    DraftPromptOut,
    PaginatedResponse,
    ReferenceAdminOut,
    ReferenceUpdate,
)
from app.services import curation, storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def _read_valid_image(file: UploadFile) -> bytes:
    if (file.content_type or "").lower() not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Image must be JPEG, PNG, or WEBP.")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large. Maximum 10MB.")
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise HTTPException(status_code=400, detail="File is not a valid image.")
    return data


# ── Reference management ──────────────────────────────────────────────

@router.get("/references", response_model=list[ReferenceAdminOut])
def list_all_references(db: Session = Depends(get_db)) -> list[ReferenceAdminOut]:
    """All references incl. inactive (admin view exposes the prompt)."""
    rows = db.scalars(select(ReferencePhoto).order_by(ReferencePhoto.created_at.desc())).all()
    return [ReferenceAdminOut.model_validate(r) for r in rows]


@router.post("/references/draft-prompt", response_model=DraftPromptOut)
async def draft_reference_prompt(image: UploadFile = File(...)) -> DraftPromptOut:
    """Auto-write a prompt from an uploaded image (Gemini). Does not save anything."""
    data = await _read_valid_image(image)
    try:
        draft = await curation.draft_from_image(data, image.content_type or "image/jpeg")
    except curation.CurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return DraftPromptOut(**draft)


@router.post("/references", response_model=ReferenceAdminOut, status_code=201)
async def create_reference(
    image: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=200),
    prompt_template: str = Form(..., min_length=1, max_length=2000),
    collection: Optional[str] = Form(None),
    db: Session = Depends(get_db),
) -> ReferenceAdminOut:
    """Create a reference: the uploaded image becomes the cover thumbnail."""
    data = await _read_valid_image(image)
    thumbnail_url = storage.save_bytes("thumbnails", image.filename or "ref.jpg", data)

    ref = ReferencePhoto(
        title=title.strip(),
        collection=(collection or "").strip() or None,
        thumbnail_url=thumbnail_url,
        style_description={},
        prompt_template=prompt_template.strip(),
        active=True,
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    clear_references_cache()
    logger.info("Reference created: id=%s, title=%s", ref.id, ref.title)
    return ReferenceAdminOut.model_validate(ref)


@router.patch("/references/{ref_id}", response_model=ReferenceAdminOut)
def update_reference(
    ref_id: str,
    body: ReferenceUpdate,
    db: Session = Depends(get_db),
) -> ReferenceAdminOut:
    """Edit fields or activate/deactivate a reference (deactivate hides it from users)."""
    ref = db.get(ReferencePhoto, ref_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Reference not found")

    if body.title is not None:
        ref.title = body.title.strip()
    if body.collection is not None:
        ref.collection = body.collection.strip() or None
    if body.prompt_template is not None:
        ref.prompt_template = body.prompt_template.strip()
    if body.active is not None:
        ref.active = body.active
    db.commit()
    db.refresh(ref)
    clear_references_cache()
    return ReferenceAdminOut.model_validate(ref)


@router.delete("/references/{ref_id}", status_code=204)
def delete_reference(ref_id: str, db: Session = Depends(get_db)) -> None:
    """Hard-delete a reference. If generations reference it, 409 — deactivate instead."""
    ref = db.get(ReferencePhoto, ref_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Reference not found")
    try:
        db.delete(ref)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This reference has generations attached. Deactivate it instead of deleting.",
        )
    clear_references_cache()
    logger.info("Reference deleted: id=%s", ref_id)


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
