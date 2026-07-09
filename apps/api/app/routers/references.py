from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.reference_photo import ReferencePhoto
from app.schemas import ReferencePhotoOut

router = APIRouter(prefix="/api/references", tags=["references"])


@router.get("", response_model=list[ReferencePhotoOut])
def list_references(db: Session = Depends(get_db)) -> list[ReferencePhoto]:
    stmt = select(ReferencePhoto).where(ReferencePhoto.active.is_(True)).order_by(ReferencePhoto.created_at)
    return list(db.scalars(stmt).all())