"""跨任务附件简历监视。"""

from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path
from typing import Any

from resume_agent.api_client import ApiClient


class ResumeMonitor:
    def __init__(
        self,
        api: ApiClient,
        *,
        download_attachment: Callable[[int, str, str], Path | None],
    ) -> None:
        self.api = api
        self._download_attachment = download_attachment
        self._pending_files: dict[int, Path] = {}
        self._file_hashes: dict[int, str] = {}

    @staticmethod
    def _valid_pdf(path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                return handle.read(5) == b"%PDF-"
        except OSError:
            return False

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def poll_once(self) -> int:
        uploaded = 0
        for candidate in self.api.list_resume_inbox():
            candidate_id = int(candidate["candidate_id"])
            waiting_jobs = list(candidate.get("waiting_jobs") or [])
            if not waiting_jobs:
                continue
            path = self._pending_files.get(candidate_id)
            if path is None or not path.exists():
                path = self._download_attachment(
                    candidate_id,
                    str(candidate["candidate_name"]),
                    str(candidate.get("boss_id") or ""),
                )
            if path is None:
                continue
            if not self._valid_pdf(path):
                path.unlink(missing_ok=True)
                self._pending_files.pop(candidate_id, None)
                self._file_hashes.pop(candidate_id, None)
                continue
            self._pending_files[candidate_id] = path
            self._file_hashes[candidate_id] = self._sha256(path)
            contact_event_id = int(waiting_jobs[0]["contact_event_id"])
            try:
                self.api.upload_agent_resume(
                    path,
                    candidate_id=candidate_id,
                    contact_event_id=contact_event_id,
                )
            except Exception:
                continue
            path.unlink(missing_ok=True)
            self._pending_files.pop(candidate_id, None)
            self._file_hashes.pop(candidate_id, None)
            uploaded += 1
        return uploaded
