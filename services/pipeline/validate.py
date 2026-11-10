from __future__ import annotations

from pathlib import Path

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


class UploadRejected(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def assert_upload_allowed(
    *,
    filename: str,
    size: int,
    max_bytes: int,
    duration: float | None = None,
    max_seconds: float | None = None,
) -> None:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadRejected(
            "bad_type",
            f"Unsupported file type '{ext or 'none'}'. Upload mp4, mov, mkv, or webm.",
        )
    if size > max_bytes:
        raise UploadRejected(
            "too_large",
            f"File is {size} bytes, over the limit of {max_bytes} bytes.",
            status=413,
        )
    if duration is not None and max_seconds is not None and duration > max_seconds:
        raise UploadRejected(
            "too_long",
            f"Video is {duration:.1f}s, over the limit of {max_seconds:.0f}s.",
        )
