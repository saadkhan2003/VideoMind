from __future__ import annotations

import subprocess
from pathlib import Path


class MediaError(Exception):
    pass


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-800:]
        raise MediaError(tail or f"command failed: {' '.join(cmd[:3])}")


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise MediaError("ffprobe could not read the file. It is not a supported video.")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise MediaError("ffprobe returned a non-numeric duration") from exc


def extract_audio(video: Path, wav: Path) -> None:
    wav.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-vn",
            str(wav),
        ]
    )


def grab_frame(video: Path, timestamp: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{max(0.0, timestamp):.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(dest),
        ]
    )
