"""Reference photos router with fast in-memory caching and HTTP Cache-Control support."""
import logging
import time
from typing import List

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.reference_photo import ReferencePhoto
from app.schemas import ReferencePhotoOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/references", tags=["references"])

# Simple in-memory cache for reference presets (60-second TTL)
_CACHE_TTL_SECONDS = 60
_cache_data: List[ReferencePhotoOut] = []
_cache_timestamp: float = 0.0


def clear_references_cache():
    """Clear in-memory reference cache when presets are seeded or modified."""
    global _cache_timestamp
    _cache_timestamp = 0.0


@router.get("", response_model=list[ReferencePhotoOut])
def list_references(
    response: Response,
    db: Session = Depends(get_db),
) -> list[ReferencePhotoOut]:
    """Return catalog of active reference photo presets.
    
    Includes 60-second server-side in-memory caching and browser Cache-Control headers
    for instant frontend loading.
    """
    global _cache_data, _cache_timestamp

    now = time.monotonic()
    
    # Return from server in-memory cache if valid
    if _cache_data and (now - _cache_timestamp) < _CACHE_TTL_SECONDS:
        response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
        logger.debug("Serving reference catalog from in-memory cache (%d presets)", len(_cache_data))
        return _cache_data

    # Query active presets from database
    stmt = (
        select(ReferencePhoto)
        .where(ReferencePhoto.active.is_(True))
        .order_by(ReferencePhoto.created_at)
    )
    raw_results = list(db.scalars(stmt).all())
    
    # Convert to schema objects for clean caching
    _cache_data = [ReferencePhotoOut.model_validate(r) for r in raw_results]
    _cache_timestamp = now

    # Enable browser HTTP caching
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    logger.info("Refreshed reference catalog cache from DB: returned %d active presets", len(_cache_data))
    return _cache_data