import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    logger.debug("Health check pinged")
    return {"status": "ok"}