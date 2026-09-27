"""FastAPI 入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from resume_api.core.config import ensure_data_dirs, get_settings
from resume_api.core.db import SessionLocal, init_db
from resume_api.routers import (
    agent,
    auth,
    candidate_merges,
    candidates,
    events,
    jobs,
    outreach,
    resumes,
    reviews,
    scoring,
    screening_tasks,
)
from resume_api.services.folder_watch import FolderWatcher

_watcher: FolderWatcher | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _watcher
    settings = get_settings()
    ensure_data_dirs(settings)
    init_db()
    if settings.is_development:
        _watcher = FolderWatcher(settings, SessionLocal)
        _watcher.start()
    yield
    if _watcher:
        _watcher.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="Resume Screening API", lifespan=lifespan)
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(auth.router)
    application.include_router(jobs.router)
    application.include_router(candidates.router)
    application.include_router(candidate_merges.router)
    application.include_router(events.router)
    application.include_router(resumes.router)
    application.include_router(agent.router)
    application.include_router(scoring.router)
    application.include_router(reviews.router)
    application.include_router(screening_tasks.router)
    application.include_router(outreach.router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
