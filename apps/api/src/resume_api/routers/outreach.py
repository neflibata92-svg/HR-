"""联系预留、结果确认和人工重发授权路由。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from resume_api.core.auth import CurrentUser, require_lead_or_admin, require_password_change_complete
from resume_api.core.db import get_db
from resume_api.schemas import (
    OutreachFailRequest,
    OutreachOverrideCreate,
    OutreachOverrideOut,
    OutreachReservationCreate,
    OutreachReservationOut,
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
        if payload.task_id is None and user.role != "admin":
            raise HTTPException(status_code=403, detail="task_id is required for member outreach")
        if payload.task_id is not None:
            task_service.require_task_access(
                db, payload.task_id, actor_user_id=user.id, actor_role=user.role
            )
        return OutreachReservationOut.model_validate(outreach_service.reserve(db, payload))
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
