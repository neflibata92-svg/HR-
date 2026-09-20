"""简历入库。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from resume_api.core.config import Settings
from resume_api.models import Resume
from resume_api.parsing import parse_resume_file


def store_resume_file(
    db: Session,
    settings: Settings,
    *,
    src_path: Path,
    original_name: str,
    source: str,
    candidate_id: int | None = None,
) -> Resume:
    storage = Path(settings.storage_dir)
    storage.mkdir(parents=True, exist_ok=True)
    dest = storage / f"{uuid.uuid4().hex}_{original_name}"
    shutil.copy2(src_path, dest)
    text, status = parse_resume_file(dest)
    resume = Resume(
        candidate_id=candidate_id,
        file_path=str(dest),
        parsed_text=text,
        source=source,
        parse_status=status,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume
