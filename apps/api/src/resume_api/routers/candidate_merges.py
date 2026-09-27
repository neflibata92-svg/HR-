"""候选人合并、预览、建议与撤销路由。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from resume_api.core.auth import (
    CurrentUser,
    require_lead_or_admin,
    require_password_change_complete,
)
from resume_api.core.db import get_db
from resume_api.schemas import (
    CandidateMergeOut,
    CandidateMergePreviewOut,
    CandidateMergeRequest,
    CandidateMergeRevertOut,
    CandidateMergeSuggestionCreate,
    CandidateMergeSuggestionOut,
)
from resume_api.services import candidate_merges as merge_service

router = APIRouter(prefix="/api/candidate-merges", tags=["candidate-merges"])


def _translate_error(exc: merge_service.MergeError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post(
    "/suggestions",
    response_model=CandidateMergeSuggestionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_suggestion(
    payload: CandidateMergeSuggestionCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_password_change_complete),
) -> CandidateMergeSuggestionOut:
    try:
        suggestion = merge_service.create_suggestion(
            db, payload, actor_user_id=current_user.id
        )
    except merge_service.MergeError as exc:
        raise _translate_error(exc) from exc
    return CandidateMergeSuggestionOut.model_validate(suggestion)


@router.post("/preview", response_model=CandidateMergePreviewOut)
def preview_merge(
    payload: CandidateMergeRequest,
    db: Session = Depends(get_db),
    _current_user: CurrentUser = Depends(require_lead_or_admin),
) -> CandidateMergePreviewOut:
    try:
        result = merge_service.preview_merge(db, payload)
    except merge_service.MergeError as exc:
        raise _translate_error(exc) from exc
    return CandidateMergePreviewOut.model_validate(result)


@router.post(
    "",
    response_model=CandidateMergeOut,
    status_code=status.HTTP_201_CREATED,
)
def execute_merge(
    payload: CandidateMergeRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_lead_or_admin),
) -> CandidateMergeOut:
    try:
        merge, idempotent = merge_service.execute_merge(
            db, payload, actor_user_id=current_user.id
        )
    except merge_service.MergeError as exc:
        from resume_api.services.audit import add_audit_event

        add_audit_event(
            db,
            actor_user_id=current_user.id,
            action="candidate_merge.execute",
            entity_type="candidate_merge",
            entity_id="pending",
            details={
                "source_candidate_id": payload.source_candidate_id,
                "target_candidate_id": payload.target_candidate_id,
                "result": "validation_failed",
                "status_code": exc.status_code,
            },
        )
        db.commit()
        raise _translate_error(exc) from exc
    if idempotent:
        response.status_code = status.HTTP_200_OK
    return CandidateMergeOut(
        id=merge.id,
        source_candidate_id=merge.source_candidate_id,
        target_candidate_id=merge.target_candidate_id,
        field_choices=json.loads(merge.field_choices_json),
        status=merge.status,
        performed_by_user_id=merge.performed_by_user_id,
        performed_at=merge.performed_at,
    )


@router.post("/{merge_id}/revert", response_model=CandidateMergeRevertOut)
def revert_merge(
    merge_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_lead_or_admin),
) -> CandidateMergeRevertOut:
    try:
        merge, idempotent = merge_service.revert_merge(
            db, merge_id, actor_user_id=current_user.id
        )
    except merge_service.MergeError as exc:
        raise _translate_error(exc) from exc
    return CandidateMergeRevertOut(
        id=merge.id,
        status=merge.status,
        reverted=True,
        idempotent=idempotent,
    )
