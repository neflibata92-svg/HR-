"""联系预留、结果确认和人工重发授权路由。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from resume_api.core.auth import (
    CurrentUser,
    require_admin,
    require_lead_or_admin,
    require_password_change_complete,
)
from resume_api.core.db import get_db
from resume_api.models import ScreeningRecord, ScreeningTaskItem
from resume_api.schemas import (
    OutreachFailRequest,
    OutreachOverrideCreate,
    OutreachOverrideOut,
    OutreachReservationCreate,
    OutreachReservationOut,
    OutreachUnknownOut,
    OutreachUnknownReleaseRequest,
)
from resume_api.services import outreach as outreach_service
from resume_api.services import screening_tasks as task_service

router = APIRouter(
    prefix="/api/outreach",
    tags=["outreach"],
    dependencies=[Depends(require_password_change_complete)],
)


def _error(exc: outreach_service.OutreachError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/unknown", response_model=list[OutreachUnknownOut])
def list_unknown(
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_admin),
) -> list[OutreachUnknownOut]:
    return [OutreachUnknownOut.model_validate(item) for item in outreach_service.list_unknown_outreach(db)]


@router.post("/{event_id}/release-unknown", response_model=OutreachReservationOut)
def release_unknown(
    event_id: int,
    payload: OutreachUnknownReleaseRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_admin),
) -> OutreachReservationOut:
    try:
        return OutreachReservationOut.model_validate(
            outreach_service.release_unknown_after_admin_review(
                db,
                event_id,
                admin_user_id=user.id,
                reason=payload.reason,
            )
        )
    except outreach_service.OutreachError as exc:
        raise _error(exc) from exc


@router.post(
    "/reservations",
    response_model=OutreachReservationOut,
    status_code=status.HTTP_201_CREATED,
)
def reserve(
    payload: OutreachReservationCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> OutreachReservationOut:
    try:
        effective_task_id = payload.task_id
        if payload.task_item_id is not None:
            item = db.get(ScreeningTaskItem, payload.task_item_id)
            if item is None:
                raise HTTPException(status_code=404, detail="screening task item not found")
            if effective_task_id is not None and item.task_id != effective_task_id:
                raise HTTPException(status_code=409, detail="task item does not match task")
            effective_task_id = item.task_id
        if payload.screening_record_id is not None:
            record = db.get(ScreeningRecord, payload.screening_record_id)
            if record is not None:
                if effective_task_id is not None and record.task_id != effective_task_id:
                    raise HTTPException(status_code=409, detail="screening record does not match task")
                effective_task_id = effective_task_id or record.task_id
        if effective_task_id is None and user.role != "admin":
            raise HTTPException(status_code=403, detail="task_id is required for member outreach")
        if effective_task_id is not None:
            task_service.require_task_access(
                db, effective_task_id, actor_user_id=user.id, actor_role=user.role
            )
        return OutreachReservationOut.model_validate(
            outreach_service.reserve(db, payload, actor_user_id=user.id)
        )
    except (outreach_service.OutreachError, task_service.ScreeningTaskError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/{event_id}/confirm", response_model=OutreachReservationOut)
def confirm(
    event_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> OutreachReservationOut:
    try:
        outreach_service.require_outreach_access(
            db, event_id, actor_user_id=user.id, actor_role=user.role
        )
        return OutreachReservationOut.model_validate(outreach_service.confirm(db, event_id))
    except outreach_service.OutreachError as exc:
        raise _error(exc) from exc


@router.post("/{event_id}/fail", response_model=OutreachReservationOut)
def fail(
    event_id: int,
    payload: OutreachFailRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> OutreachReservationOut:
    try:
        outreach_service.require_outreach_access(
            db, event_id, actor_user_id=user.id, actor_role=user.role
        )
        return OutreachReservationOut.model_validate(
            outreach_service.fail(db, event_id, reason=payload.reason)
        )
    except outreach_service.OutreachError as exc:
        raise _error(exc) from exc


@router.post("/{event_id}/unknown", response_model=OutreachReservationOut)
def mark_unknown(
    event_id: int,
    payload: OutreachFailRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> OutreachReservationOut:
    try:
        outreach_service.require_outreach_access(
            db, event_id, actor_user_id=user.id, actor_role=user.role
        )
        return OutreachReservationOut.model_validate(
            outreach_service.mark_unknown(db, event_id, reason=payload.reason)
        )
    except outreach_service.OutreachError as exc:
        raise _error(exc) from exc


@router.post(
    "/overrides",
    response_model=OutreachOverrideOut,
    status_code=status.HTTP_201_CREATED,
)
def create_override(
    payload: OutreachOverrideCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_lead_or_admin),
) -> OutreachOverrideOut:
    return OutreachOverrideOut.model_validate(
        outreach_service.create_override(db, payload, user_id=user.id)
    )
