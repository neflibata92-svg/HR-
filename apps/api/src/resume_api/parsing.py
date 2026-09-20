"""简历文本解析。"""

from __future__ import annotations

from pathlib import Path


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def parse_resume_file(path: Path) -> tuple[str, str]:
    """返回 (parsed_text, parse_status)。"""

    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "", "skipped_image"
    if suffix == ".txt":
        try:
            return path.read_text(encoding="utf-8", errors="ignore"), "ok"
        except OSError:
            return "", "failed"
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts = [(page.extract_text() or "") for page in reader.pages]
            return "\n".join(parts).strip(), "ok"
        except Exception:
            return "", "failed"
    if suffix in {".docx"}:
        try:
            import docx

            document = docx.Document(str(path))
            text = "\n".join(p.text for p in document.paragraphs).strip()
            return text, "ok"
        except Exception:
            return "", "failed"
    try:
        return path.read_text(encoding="utf-8", errors="ignore"), "ok"
    except OSError:
        return "", "failed"
