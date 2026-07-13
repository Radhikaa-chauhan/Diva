from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, engine
from app.routers import auth, dashboard, health, jobs, references

settings = get_settings()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Diva API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/storage", StaticFiles(directory=settings.storage_dir), name="storage")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(references.router)
app.include_router(jobs.router)
app.include_router(dashboard.router)