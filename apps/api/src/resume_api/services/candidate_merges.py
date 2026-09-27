"""候选人字段级合并与事务性撤销。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.models import (
    Candidate,
    CandidateJob,
    CandidateMerge,
    CandidateMergeSuggestion,
    ExchangeEvent,
    OutreachEvent,
    OutreachOverride,
    Resume,
    ScoreEvent,
    ScreeningTaskItem,
)
from resume_api.schemas import CandidateMergeRequest, CandidateMergeSuggestionCreate
from resume_api.services.audit import add_audit_event

MERGE_FIELDS = (
    "name",
    "phone_normalized",
    "email_normalized",
    "age",
    "years_of_experience",
    "source",
)
STATUS_RANK = {
    "discovered": 0,
    "scored": 1,
    "needs_review": 2,
    "eligible": 3,
    "contacted": 4,
    "resume_received": 5,
    "archived": 6,
}


class MergeError(ValueError):
    def __init__(self, status_code: int, detail: str | dict[str, object]) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def _rows(db: Session, model, candidate_ids: tuple[int, int]):
    return list(
        db.scalars(
            select(model)
            .where(model.candidate_id.in_(candidate_ids))
            .order_by(model.id)
            .with_for_update()
        ).all()
    )


def _validate_candidates(
    db: Session, source_id: int, target_id: int, *, lock: bool = False
) -> tuple[Candidate, Candidate]:
    if source_id == target_id:
        raise MergeError(422, "source and target must differ")
    stmt = select(Candidate).where(Candidate.id.in_((source_id, target_id))).order_by(Candidate.id)
    if lock:
        stmt = stmt.with_for_update()
    candidates = {row.id: row for row in db.scalars(stmt).all()}
    if source_id not in candidates or target_id not in candidates:
        raise MergeError(404, "candidate not found")
    source = candidates[source_id]
    target = candidates[target_id]
    if source.merged_into_candidate_id is not None:
        raise MergeError(409, "source candidate is already merged")
    if target.merged_into_candidate_id is not None:
        raise MergeError(409, "target candidate is already merged")
    seen: set[int] = set()
    current: Candidate | None = target
    while current is not None and current.merged_into_candidate_id is not None:
        if current.id in seen or current.merged_into_candidate_id == source_id:
            raise MergeError(409, "candidate merge would create a cycle")
        seen.add(current.id)
        current = db.get(Candidate, current.merged_into_candidate_id)
    active = db.scalar(
        select(CandidateMerge).where(
            CandidateMerge.status == "active",
            (
                CandidateMerge.source_candidate_id.in_((source_id, target_id))
                | CandidateMerge.target_candidate_id.in_((source_id, target_id))
            ),
        )
    )
    if active is not None:
        if (
            active.source_candidate_id == source_id
            and active.target_candidate_id == target_id
        ):
            raise MergeError(
                409,
                {"existing_merge_id": active.id, "reason": "identical_active_merge"},
            )
        raise MergeError(409, "candidate participates in another active merge")
    return source, target


def _merged_fields(source: Candidate, target: Candidate, payload: CandidateMergeRequest):
    choices = payload.field_choices.model_dump()
    return {
        field: getattr(source if choices[field] == "source" else target, field)
        for field in MERGE_FIELDS
    }


def _conflicts(
    resumes: list[Resume], task_items: list[ScreeningTaskItem]
) -> list[dict[str, object]]:
    conflicts: list[dict[str, object]] = []
    by_hash: dict[str, Resume] = {}
    for resume in resumes:
        if not resume.file_hash:
            continue
        other = by_hash.get(resume.file_hash)
        if other is not None and other.candidate_id != resume.candidate_id:
            conflicts.append(
                {
                    "entity_type": "resume",
                    "entity_id": resume.id,
                    "other_entity_id": other.id,
                    "reason": "duplicate_file_hash_on_merged_candidate",
                }
            )
        else:
            by_hash[resume.file_hash] = resume
    by_task: dict[int, ScreeningTaskItem] = {}
    for item in task_items:
        other = by_task.get(item.task_id)
        if other is not None and other.candidate_id != item.candidate_id:
            conflicts.append(
                {
                    "entity_type": "screening_task_item",
                    "entity_id": item.id,
                    "other_entity_id": other.id,
                    "task_id": item.task_id,
                    "reason": "same_task_candidate_collision",
                }
            )
        else:
            by_task[item.task_id] = item
    return conflicts


def _load_related(db: Session, source_id: int, target_id: int) -> dict[str, list]:
    ids = (source_id, target_id)
    return {
        "resumes": _rows(db, Resume, ids),
        "candidate_jobs": _rows(db, CandidateJob, ids),
        "score_events": _rows(db, ScoreEvent, ids),
        "task_items": _rows(db, ScreeningTaskItem, ids),
        "outreach_events": _rows(db, OutreachEvent, ids),
        "outreach_overrides": _rows(db, OutreachOverride, ids),
        "exchange_events": _rows(db, ExchangeEvent, ids),
    }


def preview_merge(db: Session, payload: CandidateMergeRequest) -> dict[str, object]:
    source, target = _validate_candidates(
        db, payload.source_candidate_id, payload.target_candidate_id
    )
    related = _load_related(db, source.id, target.id)
    return {
        "source_candidate_id": source.id,
        "target_candidate_id": target.id,
        "merged_fields": _merged_fields(source, target, payload),
        "moved_counts": {name: len(rows) for name, rows in related.items()},
        "conflicts": _conflicts(related["resumes"], related["task_items"]),
    }


def _candidate_snapshot(candidate: Candidate) -> dict[str, object]:
    fields = (
        "boss_id", "fingerprint", "name", "phone_normalized", "email_normalized",
        "age", "years_of_experience", "job_segments_json", "source",
        "merged_into_candidate_id",
    )
    return {field: getattr(candidate, field) for field in fields}


def _row_snapshot(row, fields: tuple[str, ...]) -> dict[str, object]:
    values: dict[str, object] = {"id": row.id}
    for field in fields:
        value = getattr(row, field)
        values[field] = value.isoformat() if isinstance(value, datetime) else value
    return values


def _restore_value(field: str, value: object) -> object:
    if field in {"created_at", "updated_at"} and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _snapshot(source: Candidate, target: Candidate, related: dict[str, list]) -> dict[str, object]:
    return {
        "version": 1,
        "source_candidate": {"id": source.id, "fields": _candidate_snapshot(source)},
        "target_candidate": {"id": target.id, "fields": _candidate_snapshot(target)},
        "resumes": [
            _row_snapshot(row, ("candidate_id", "version_number", "supersedes_resume_id", "file_hash"))
            for row in related["resumes"]
        ],
        "candidate_jobs": [
            {
                **_row_snapshot(
                    row,
                    (
                        "candidate_id", "job_id", "status", "active_resume_id",
                        "latest_score_event_id", "review_reason_json", "created_at",
                        "updated_at",
                    ),
                ),
                "deleted_during_merge": any(
                    other.job_id == row.job_id
                    and other.candidate_id != row.candidate_id
                    and row.candidate_id == source.id
                    for other in related["candidate_jobs"]
                ),
            }
            for row in related["candidate_jobs"]
        ],
        "score_events": [
            _row_snapshot(row, ("candidate_id", "candidate_job_id"))
            for row in related["score_events"]
        ],
        "task_items": [
            _row_snapshot(row, ("candidate_id", "candidate_job_id"))
            for row in related["task_items"]
        ],
        "outreach_events": [
            _row_snapshot(row, ("candidate_id",)) for row in related["outreach_events"]
        ],
        "outreach_overrides": [
            _row_snapshot(row, ("candidate_id",)) for row in related["outreach_overrides"]
        ],
        "exchange_events": [
            _row_snapshot(row, ("candidate_id",)) for row in related["exchange_events"]
        ],
    }


def _merge_candidate_jobs(db: Session, related: dict[str, list], source_id: int, target_id: int) -> None:
    by_job: dict[int, list[CandidateJob]] = {}
    for link in related["candidate_jobs"]:
        by_job.setdefault(link.job_id, []).append(link)
    for links in by_job.values():
        source_link = next((row for row in links if row.candidate_id == source_id), None)
        target_link = next((row for row in links if row.candidate_id == target_id), None)
        if source_link is None:
            continue
        if target_link is None:
            source_link.candidate_id = target_id
            continue
        winner = max(links, key=lambda row: STATUS_RANK.get(row.status, -1))
        target_link.status = winner.status
        target_link.active_resume_id = winner.active_resume_id or target_link.active_resume_id
        reasons: list[object] = []
        for row in links:
            try:
                values = json.loads(row.review_reason_json)
            except (TypeError, json.JSONDecodeError):
                values = []
            for value in values if isinstance(values, list) else []:
                if value not in reasons:
                    reasons.append(value)
        target_link.review_reason_json = json.dumps(reasons, ensure_ascii=False)
        scores = [row for row in related["score_events"] if row.candidate_job_id in {source_link.id, target_link.id}]
        for score in scores:
            score.candidate_job_id = target_link.id
        for item in related["task_items"]:
            if item.candidate_job_id == source_link.id:
                item.candidate_job_id = target_link.id
        if scores:
            latest = max(scores, key=lambda row: (row.created_at or datetime.min, row.id))
            target_link.latest_score_event_id = latest.id
        db.delete(source_link)


def execute_merge(
    db: Session, payload: CandidateMergeRequest, *, actor_user_id: int
) -> tuple[CandidateMerge, bool]:
    existing = db.scalar(
        select(CandidateMerge).where(
            CandidateMerge.source_candidate_id == payload.source_candidate_id,
            CandidateMerge.target_candidate_id == payload.target_candidate_id,
            CandidateMerge.status == "active",
        )
    )
    if existing is not None:
        expected_choices = json.dumps(payload.field_choices.model_dump())
        if existing.field_choices_json == expected_choices:
            return existing, True
        raise MergeError(409, "same candidate pair has a different active merge")
    try:
        source, target = _validate_candidates(
            db, payload.source_candidate_id, payload.target_candidate_id, lock=True
        )
        related = _load_related(db, source.id, target.id)
        conflicts = _conflicts(related["resumes"], related["task_items"])
        if conflicts:
            raise MergeError(409, {"conflicts": conflicts})
        snapshot = _snapshot(source, target, related)
        merge = CandidateMerge(
            source_candidate_id=source.id,
            target_candidate_id=target.id,
            field_choices_json=json.dumps(payload.field_choices.model_dump()),
            snapshot_json=json.dumps(snapshot, ensure_ascii=False),
            performed_by_user_id=actor_user_id,
        )
        db.add(merge)
        db.flush()
        for field, value in _merged_fields(source, target, payload).items():
            setattr(target, field, value)
        resumes = sorted(related["resumes"], key=lambda row: (row.created_at, row.id))
        for index, resume in enumerate(resumes, 1):
            resume.version_number = -index
        db.flush()
        previous: Resume | None = None
        for index, resume in enumerate(resumes, 1):
            resume.candidate_id = target.id
            resume.version_number = index
            resume.supersedes_resume_id = previous.id if previous else None
            previous = resume
        _merge_candidate_jobs(db, related, source.id, target.id)
        for name in (
            "score_events",
            "task_items",
            "outreach_events",
            "outreach_overrides",
            "exchange_events",
        ):
            for row in related[name]:
                row.candidate_id = target.id
        source.merged_into_candidate_id = target.id
        db.flush()
        deleted_job_ids = {
            row["id"]
            for row in snapshot["candidate_jobs"]
            if row["deleted_during_merge"]
        }
        snapshot["post_candidate_jobs"] = [
            _row_snapshot(
                row,
                (
                    "candidate_id", "job_id", "status", "active_resume_id",
                    "latest_score_event_id", "review_reason_json",
                ),
            )
            for row in related["candidate_jobs"]
            if row.id not in deleted_job_ids
        ]
        merge.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
        add_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="candidate_merge.execute",
            entity_type="candidate_merge",
            entity_id=str(merge.id),
            details={"source_candidate_id": source.id, "target_candidate_id": target.id, "result": "success"},
        )
        db.commit()
        db.refresh(merge)
        return merge, False
    except MergeError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def create_suggestion(
    db: Session, payload: CandidateMergeSuggestionCreate, *, actor_user_id: int
) -> CandidateMergeSuggestion:
    if payload.source_candidate_id == payload.target_candidate_id:
        raise MergeError(422, "source and target must differ")
    source_id, target_id = sorted((payload.source_candidate_id, payload.target_candidate_id))
    if db.get(Candidate, source_id) is None or db.get(Candidate, target_id) is None:
        raise MergeError(404, "candidate not found")
    existing = db.scalar(
        select(CandidateMergeSuggestion).where(
            CandidateMergeSuggestion.source_candidate_id == source_id,
            CandidateMergeSuggestion.target_candidate_id == target_id,
        )
    )
    if existing is not None:
        return existing
    suggestion = CandidateMergeSuggestion(
        source_candidate_id=source_id,
        target_candidate_id=target_id,
        suggested_by_user_id=actor_user_id,
        match_reason_json=json.dumps(payload.reasons, ensure_ascii=False),
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


def _new_record_conflicts(db: Session, snapshot: dict[str, object], target_id: int):
    conflicts: list[dict[str, object]] = []
    models = {
        "resumes": (Resume, "resume"),
        "candidate_jobs": (CandidateJob, "candidate_job"),
        "score_events": (ScoreEvent, "score_event"),
        "task_items": (ScreeningTaskItem, "screening_task_item"),
        "outreach_events": (OutreachEvent, "outreach_event"),
        "outreach_overrides": (OutreachOverride, "outreach_override"),
        "exchange_events": (ExchangeEvent, "exchange_event"),
    }
    for key, (model, entity_type) in models.items():
        original_ids = {row["id"] for row in snapshot[key]}
        current_ids = set(db.scalars(select(model.id).where(model.candidate_id == target_id)).all())
        for entity_id in sorted(current_ids - original_ids):
            conflicts.append(
                {"entity_type": entity_type, "entity_id": entity_id, "reason": "created_after_merge"}
            )
    return conflicts


def revert_merge(db: Session, merge_id: int, *, actor_user_id: int) -> tuple[CandidateMerge, bool]:
    merge = db.scalar(
        select(CandidateMerge).where(CandidateMerge.id == merge_id).with_for_update()
    )
    if merge is None:
        raise MergeError(404, "candidate merge not found")
    if merge.status == "reverted":
        add_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="candidate_merge.revert",
            entity_type="candidate_merge",
            entity_id=str(merge.id),
            details={"result": "idempotent"},
        )
        db.commit()
        return merge, True
    snapshot = json.loads(merge.snapshot_json)
    candidate_ids = (merge.source_candidate_id, merge.target_candidate_id)
    list(
        db.scalars(
            select(Candidate)
            .where(Candidate.id.in_(candidate_ids))
            .order_by(Candidate.id)
            .with_for_update()
        ).all()
    )
    _load_related(db, *candidate_ids)
    later_active = db.scalar(
        select(CandidateMerge).where(
            CandidateMerge.id != merge.id,
            CandidateMerge.status == "active",
            (
                CandidateMerge.source_candidate_id.in_(candidate_ids)
                | CandidateMerge.target_candidate_id.in_(candidate_ids)
            ),
        )
    )
    conflicts = _new_record_conflicts(db, snapshot, merge.target_candidate_id)
    for expected in snapshot.get("post_candidate_jobs", []):
        current = db.get(CandidateJob, expected["id"])
        if current is None:
            continue
        fields = (
            "candidate_id", "job_id", "status", "active_resume_id",
            "latest_score_event_id", "review_reason_json",
        )
        if any(getattr(current, field) != expected[field] for field in fields):
            conflicts.append(
                {
                    "entity_type": "candidate_job",
                    "entity_id": current.id,
                    "reason": "modified_after_merge",
                }
            )
    if later_active is not None:
        conflicts.append(
            {
                "entity_type": "candidate_merge",
                "entity_id": later_active.id,
                "reason": "dependent_active_merge",
            }
        )
    for row in snapshot["candidate_jobs"]:
        if not row.get("deleted_during_merge"):
            continue
        current = db.get(CandidateJob, row["id"])
        if current is not None:
            conflicts.append(
                {
                    "entity_type": "candidate_job",
                    "entity_id": row["id"],
                    "reason": "id_reused",
                }
            )
    if conflicts:
        db.rollback()
        add_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="candidate_merge.revert",
            entity_type="candidate_merge",
            entity_id=str(merge.id),
            details={"result": "conflict", "conflict_count": len(conflicts)},
        )
        db.commit()
        raise MergeError(409, {"conflicts": conflicts})
    try:
        for row in snapshot["candidate_jobs"]:
            link = db.get(CandidateJob, row["id"])
            if link is None:
                link = CandidateJob(id=row["id"], job_id=row["job_id"], candidate_id=row["candidate_id"])
                db.add(link)
            for field, value in row.items():
                if field not in {"id", "deleted_during_merge"}:
                    setattr(link, field, _restore_value(field, value))
        db.flush()
        for key, model in (
            ("score_events", ScoreEvent),
            ("task_items", ScreeningTaskItem),
            ("outreach_events", OutreachEvent),
            ("outreach_overrides", OutreachOverride),
            ("exchange_events", ExchangeEvent),
        ):
            for row in snapshot[key]:
                entity = db.get(model, row["id"])
                if entity is None:
                    raise MergeError(409, {"conflicts": [{"entity_type": key, "entity_id": row["id"], "reason": "missing_original_record"}]})
                for field, value in row.items():
                    if field != "id":
                        setattr(entity, field, value)
        resumes = [db.get(Resume, row["id"]) for row in snapshot["resumes"]]
        for index, resume in enumerate(resumes, 1):
            if resume is None:
                raise MergeError(409, {"conflicts": [{"entity_type": "resume", "reason": "missing_original_record"}]})
            resume.version_number = -index
        db.flush()
        for row, resume in zip(snapshot["resumes"], resumes, strict=True):
            for field, value in row.items():
                if field != "id":
                    setattr(resume, field, value)
        for key in ("source_candidate", "target_candidate"):
            candidate_data = snapshot[key]
            candidate = db.get(Candidate, candidate_data["id"])
            for field, value in candidate_data["fields"].items():
                setattr(candidate, field, value)
        merge.status = "reverted"
        merge.reverted_by_user_id = actor_user_id
        merge.reverted_at = datetime.now(timezone.utc)
        add_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="candidate_merge.revert",
            entity_type="candidate_merge",
            entity_id=str(merge.id),
            details={"result": "success"},
        )
        db.commit()
        db.refresh(merge)
        return merge, False
    except MergeError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
