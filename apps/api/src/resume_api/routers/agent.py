"""Agent 运行状态路由。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.core.auth import CurrentUser, require_password_change_complete
from resume_api.core.db import get_db
from resume_api.models import AgentRun
from resume_api.schemas import AgentRunOut, AgentRunUpsert

router = APIRouter(
    prefix="/api/agent",
    tags=["agent"],
    dependencies=[Depends(require_password_change_complete)],
)


@router.post("/runs", response_model=AgentRunOut)
def upsert_run(
    payload: AgentRunUpsert,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> AgentRunOut:
    run = db.scalar(select(AgentRun).where(AgentRun.machine_id == payload.machine_id))
    if run is None:
        run = AgentRun(machine_id=payload.machine_id, owner_user_id=user.id)
        db.add(run)
    elif run.owner_user_id not in (None, user.id):
        raise HTTPException(status_code=409, detail="agent belongs to another user")
    run.owner_user_id = user.id
    fields_set = payload.model_fields_set
    run.status = payload.status
    if "availability" in fields_set:
        run.availability = payload.availability or run.availability
    elif run.current_task_id is None:
        run.availability = "idle" if payload.status == "idle" else "busy"
    if "current_task_id" in fields_set:
        run.current_task_id = payload.current_task_id
    if "current_job_id" in fields_set:
        run.current_job_id = payload.current_job_id
    if run.current_task_id is not None:
        run.availability = "busy"
    if "boss_login_status" in fields_set:
        run.boss_login_status = payload.boss_login_status
    if "last_error" in fields_set:
        run.last_error = payload.last_error
    run.last_heartbeat = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return AgentRunOut.model_validate(run)


@router.patch("/runs/{machine_id}", response_model=AgentRunOut)
def patch_run(
    machine_id: str,
    payload: AgentRunUpsert,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> AgentRunOut:
    payload.machine_id = machine_id
    return upsert_run(payload, db, user)


@router.get("/runs", response_model=list[AgentRunOut])
def list_runs(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> list[AgentRunOut]:
    rows = list(
        db.scalars(
            select(AgentRun)
            .where(AgentRun.owner_user_id == user.id)
            .order_by(AgentRun.id.desc())
        ).all()
    )
    return [AgentRunOut.model_validate(r) for r in rows]
