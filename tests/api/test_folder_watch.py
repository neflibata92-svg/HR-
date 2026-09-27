from pathlib import Path

from resume_api.core import config as config_mod
from resume_api.core import db as db_mod
from resume_api.models import Resume
from resume_api.services.folder_watch import FolderWatcher


def test_folder_watch_stable_file(client, auth_headers) -> None:
    real_settings = config_mod.get_settings()
    inbox = Path(real_settings.watch_dir)
    target = inbox / "watch_me.txt"
    target.write_text("folder watch content", encoding="utf-8")

    watcher = FolderWatcher(real_settings, db_mod.SessionLocal, poll_seconds=0.1)
    assert watcher.tick_once() == []
    created = watcher.tick_once()
    assert len(created) == 1
    assert not target.exists()

    db = db_mod.SessionLocal()
    try:
        resume = db.get(Resume, created[0])
        assert resume is not None
        assert resume.candidate_id is None
        assert resume.version_number is None
        assert resume.original_filename == "watch_me.txt"
        assert resume.file_hash is not None
        assert Path(resume.file_path).is_file()
    finally:
        db.close()
