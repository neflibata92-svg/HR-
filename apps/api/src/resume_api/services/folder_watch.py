"""共享文件夹监视入库。"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from resume_api.core.config import Settings
from resume_api.services.ingest import store_resume_file


class FolderWatcher:
    """轮询目录，文件大小稳定后入库。"""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        poll_seconds: float = 2.0,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_sizes: dict[str, int] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="folder-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def tick_once(self) -> list[int]:
        """处理一轮，返回新建 resume id 列表（便于测试）。"""

        inbox = Path(self.settings.watch_dir)
        inbox.mkdir(parents=True, exist_ok=True)
        created: list[int] = []
        for path in inbox.iterdir():
            if not path.is_file():
                continue
            key = str(path.resolve())
            size = path.stat().st_size
            prev = self._seen_sizes.get(key)
            self._seen_sizes[key] = size
            if prev is None or prev != size:
                continue
            db = self.session_factory()
            try:
                resume = store_resume_file(
                    db,
                    self.settings,
                    src_path=path,
                    original_name=path.name,
                    source="folder_watch",
                )
                created.append(resume.id)
                path.unlink(missing_ok=True)
                self._seen_sizes.pop(key, None)
            finally:
                db.close()
        return created

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception:
                pass
            time.sleep(self.poll_seconds)
