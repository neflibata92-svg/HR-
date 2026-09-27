"""筛选任务管理与 Agent 领取路由。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.core.auth import CurrentUser, require_password_change_complete
from resume_api.core.db import get_db
from resume_api.models import ScreeningTask, ScreeningTaskItem
from resume_api.schemas import (
    ScreeningRecordComplete,
    ScreeningRecordCreate,
    ScreeningRecordOut,
    ScreeningTaskCreate,
    ScreeningTaskItemOut,
    ScreeningTaskOut,
    TaskClaimRequest,
    TaskCompleteRequest,
    TaskItemComplete,
    TaskItemCreate,
    TaskItemFail,
    TaskPauseRequest,
)
from resume_api.services import screening_tasks as task_service

router = APIRouter(
    prefix="/api/screening-tasks",
    tags=["screening-tasks"],
    dependencies=[Depends(require_password_change_complete)],
)


def _error(exc: task_service.ScreeningTaskError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _task_out(task: ScreeningTask) -> ScreeningTaskOut:
    return ScreeningTaskOut(
        id=task.id,
        job_id=task.job_id,
        created_by_user_id=task.created_by_user_id,
        machine_id=task.machine_id,
        assigned_agent_run_id=task.assigned_agent_run_id,
        active_job_guard=task.active_job_guard,
        control_requested_at=task.control_requested_at,
        requested_count=task.requested_count,
        critical_fields=json.loads(task.critical_fields_json or "[]"),
        critical_fields_source=json.loads(task.critical_fields_source_json or "{}"),
        job_name_snapshot=task.job_name_snapshot,
        jd_text_snapshot=task.jd_text_snapshot,
        score_threshold_snapshot=task.score_threshold_snapshot,
        greet_template_snapshot=task.greet_template_snapshot,
        boss_entry_url=task.boss_entry_url_snapshot,
        status=task.status,
        pause_reason=task.pause_reason,
        processed_count=task.processed_count,
        eligible_count=task.eligible_count,
        contacted_count=task.contacted_count,
        review_count=task.review_count,
        skipped_count=task.skipped_count,
        failed_count=task.failed_count,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


def _record_out(record, *, hit: bool = False) -> ScreeningRecordOut:
    return ScreeningRecordOut(
        id=record.id,
        task_id=record.task_id,
        job_id=record.job_id,
        boss_id=record.boss_id,
        fingerprint=record.fingerprint,
        display_name=record.display_name,
        source_payload=json.loads(record.source_payload_json or "{}"),
        position_index=record.position_index,
        status=record.status,
        candidate_id=record.candidate_id,
        outreach_event_id=record.outreach_event_id,
        score_snapshot=json.loads(record.score_snapshot_json or "{}"),
        idempotent_hit=hit,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _item_out(item: ScreeningTaskItem, job_id: int, *, hit: bool = False) -> ScreeningTaskItemOut:
    return ScreeningTaskItemOut(
        id=item.id,
        task_id=item.task_id,
        candidate_id=item.candidate_id,
        candidate_job_id=item.candidate_job_id,
        job_id=job_id,
        position_index=item.position_index,
        status=item.status,
        score_event_id=item.score_event_id,
        outreach_event_id=item.outreach_event_id,
        failure_code=item.failure_code,
        failure_detail=item.failure_detail,
        idempotent_hit=hit,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("", response_model=ScreeningTaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: ScreeningTaskCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskOut:
    try:
        return _task_out(task_service.create_task(db, payload, user_id=user.id))
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.get("", response_model=list[ScreeningTaskOut])
def list_screening_tasks(
    job_id: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
):
    statement = select(ScreeningTask).order_by(ScreeningTask.created_at.desc(), ScreeningTask.id.desc())
    if user.role != "admin":
        statement = statement.where(ScreeningTask.created_by_user_id == user.id)
    if job_id is not None:
        statement = statement.where(ScreeningTask.job_id == job_id)
    return [_task_out(task) for task in db.scalars(statement).all()]


@router.get("/{task_id}", response_model=ScreeningTaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskOut:
    try:
        return _task_out(
            task_service.require_task_access(
                db, task_id, actor_user_id=user.id, actor_role=user.role
            )
        )
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/claim", response_model=ScreeningTaskOut)
def claim_next(
    payload: TaskClaimRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskOut:
    try:
        return _task_out(
            task_service.claim_task(
                db,
                machine_id=payload.machine_id,
                actor_user_id=user.id,
                actor_role=user.role,
            )
        )
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/claim", response_model=ScreeningTaskOut)
def claim_one(
    task_id: int,
    payload: TaskClaimRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskOut:
    try:
        return _task_out(
            task_service.claim_task(
                db,
                task_id=task_id,
                machine_id=payload.machine_id,
                actor_user_id=user.id,
                actor_role=user.role,
            )
        )
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/control/ack", response_model=ScreeningTaskOut)
def acknowledge_task_control(
    task_id: int,
    payload: TaskClaimRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        return _task_out(
            task_service.acknowledge_control(
                db, task_id, machine_id=payload.machine_id
            )
        )
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/complete", response_model=ScreeningTaskOut)
def complete_task(
    task_id: int,
    payload: TaskCompleteRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        return _task_out(
            task_service.complete_task(db, task_id, machine_id=payload.machine_id)
        )
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/pause", response_model=ScreeningTaskOut)
def pause(
    task_id: int,
    payload: TaskPauseRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        return _task_out(task_service.transition(db, task_id, "pause", pause_reason=payload.reason))
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/resume", response_model=ScreeningTaskOut)
def resume(
    task_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        return _task_out(task_service.transition(db, task_id, "resume"))
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/cancel", response_model=ScreeningTaskOut)
def cancel(
    task_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        return _task_out(task_service.transition(db, task_id, "cancel"))
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/records", response_model=ScreeningRecordOut)
def create_record(
    task_id: int,
    payload: ScreeningRecordCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningRecordOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        record, hit = task_service.add_screening_record(
            db,
            task_id,
            machine_id=payload.machine_id,
            boss_id=payload.boss_id,
            fingerprint=payload.fingerprint,
            display_name=payload.display_name,
            source_payload=payload.source_payload,
            position_index=payload.position_index,
        )
        response.status_code = status.HTTP_200_OK if hit else status.HTTP_201_CREATED
        return _record_out(record, hit=hit)
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/records/{record_id}/complete", response_model=ScreeningRecordOut)
def complete_record(
    task_id: int,
    record_id: int,
    payload: ScreeningRecordComplete,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningRecordOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        return _record_out(
            task_service.finish_screening_record(
                db,
                task_id,
                record_id,
                machine_id=payload.machine_id,
                status=payload.status,
                score_snapshot=payload.score_snapshot,
                outreach_event_id=payload.outreach_event_id,
                failure_code=payload.failure_code,
                failure_detail=payload.failure_detail,
            )
        )
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/items", response_model=ScreeningTaskItemOut)
def create_item(
    task_id: int,
    payload: TaskItemCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskItemOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        item, hit = task_service.add_item(
            db,
            task_id,
            machine_id=payload.machine_id,
            candidate_id=payload.candidate_id,
            position_index=payload.position_index,
        )
        response.status_code = status.HTTP_200_OK if hit else status.HTTP_201_CREATED
        task = task_service.get_task(db, task_id)
        return _item_out(item, task.job_id, hit=hit)
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/items/{item_id}/complete", response_model=ScreeningTaskItemOut)
def complete_item(
    task_id: int,
    item_id: int,
    payload: TaskItemComplete,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskItemOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        item = task_service.finish_item(
            db,
            task_id,
            item_id,
            machine_id=payload.machine_id,
            status=payload.status,
            score_event_id=payload.score_event_id,
            outreach_event_id=payload.outreach_event_id,
        )
        return _item_out(item, task_service.get_task(db, task_id).job_id)
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/items/{item_id}/fail", response_model=ScreeningTaskItemOut)
def fail_item(
    task_id: int,
    item_id: int,
    payload: TaskItemFail,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScreeningTaskItemOut:
    try:
        task_service.require_task_access(
            db, task_id, actor_user_id=user.id, actor_role=user.role
        )
        item = task_service.finish_item(
            db,
            task_id,
            item_id,
            machine_id=payload.machine_id,
            status="failed",
            failure_code=payload.failure_code,
            failure_detail=payload.failure_detail,
        )
        return _item_out(item, task_service.get_task(db, task_id).job_id)
    except task_service.ScreeningTaskError as exc:
        raise _error(exc) from exc
