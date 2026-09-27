"""审计事件写入服务。"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from resume_api.models import AuditEvent


def add_audit_event(
    db: Session,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, object] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details_json=json.dumps(details or {}, ensure_ascii=False),
    )
    db.add(event)
    return event
