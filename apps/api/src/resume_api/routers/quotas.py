"""当前登录 HR 的联系额度。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from resume_api.core.auth import CurrentUser, require_password_change_complete
from resume_api.core.db import get_db
from resume_api.schemas import OutreachQuotaOut
from resume_api.services.outreach_quota import get_usage

router = APIRouter(
    prefix="/api/quotas",
    tags=["quotas"],
    dependencies=[Depends(require_password_change_complete)],
)


@router.get("/me", response_model=OutreachQuotaOut)
def my_quota(
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> OutreachQuotaOut:
    if user_id is not None:
        raise HTTPException(status_code=422, detail="user_id is not accepted")
    result = OutreachQuotaOut(**get_usage(db, user.id))
    db.commit()
    return result
