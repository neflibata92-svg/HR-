"""Agent 运行状态路由。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.core.auth import get_current_user
from resume_api.core.db import get_db
from resume_api.models import AgentRun
from resume_api.schemas import AgentRunOut, AgentRunUpsert

router = APIRouter(prefix="/api/agent", tags=["agent"], dependencies=[Depends(get_current_user)])


@router.post("/runs", response_model=AgentRunOut)
def upsert_run(payload: AgentRunUpsert, db: Session = Depends(get_db)) -> AgentRunOut:
    run = db.scalar(select(AgentRun).where(AgentRun.machine_id == payload.machine_id))
    if run is None:
        run = AgentRun(
            machine_id=payload.machine_id,
            status=payload.status,
            last_error=payload.last_error,
            last_heartbeat=datetime.now(timezone.utc),
        )
        db.add(run)
    else:
        run.status = payload.status
        run.last_error = payload.last_error
        run.last_heartbeat = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return AgentRunOut.model_validate(run)


@router.patch("/runs/{machine_id}", response_model=AgentRunOut)
def patch_run(machine_id: str, payload: AgentRunUpsert, db: Session = Depends(get_db)) -> AgentRunOut:
    payload.machine_id = machine_id
    return upsert_run(payload, db)


@router.get("/runs", response_model=list[AgentRunOut])
def list_runs(db: Session = Depends(get_db)) -> list[AgentRunOut]:
    rows = list(db.scalars(select(AgentRun).order_by(AgentRun.id.desc())).all())
    return [AgentRunOut.model_validate(r) for r in rows]
