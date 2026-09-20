"""统一后端评分接口。"""

from fastapi import APIRouter, Depends, HTTPException, status

from resume_api.core.auth import require_password_change_complete
from resume_api.core.config import Settings, get_settings
from resume_api.schemas import ScoreEvaluateOut, ScoreEvaluateRequest
from resume_api.services import llm as llm_service

router = APIRouter(
    prefix="/api/scoring",
    tags=["scoring"],
    dependencies=[Depends(require_password_change_complete)],
)


@router.post("/evaluate", response_model=ScoreEvaluateOut)
def evaluate(
    payload: ScoreEvaluateRequest,
    settings: Settings = Depends(get_settings),
) -> ScoreEvaluateOut:
    try:
        result = llm_service.score_candidate(settings, payload.jd, payload.summary)
    except llm_service.LlmNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider is not configured",
        ) from exc
    except llm_service.LlmUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM provider request failed",
        ) from exc
    return ScoreEvaluateOut.model_validate(result.model_dump())
