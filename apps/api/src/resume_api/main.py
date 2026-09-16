"""FastAPI 入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from resume_api.core.config import ensure_data_dirs, get_settings
from resume_api.core.db import SessionLocal, init_db
from resume_api.routers import agent, candidates, events, jobs, resumes
from resume_api.services.folder_watch import FolderWatcher

_watcher: FolderWatcher | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _watcher
    settings = get_settings()
    ensure_data_dirs(settings)
    init_db()
    _watcher = FolderWatcher(settings, SessionLocal)
    _watcher.start()
    yield
    if _watcher:
        _watcher.stop()


app = FastAPI(title="Resume Screening API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(events.router)
app.include_router(resumes.router)
app.include_router(agent.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
