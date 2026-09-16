"""候选人弱指纹。"""

from __future__ import annotations

import hashlib
import re


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def candidate_fingerprint(name: str, recent_org: str) -> str:
    """姓名 + 近期组织规范化后做 SHA256。"""

    raw = f"{_norm(name)}|{_norm(recent_org)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
