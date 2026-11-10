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


# ffmpeg's mjpeg encoder fails when -ss lands within about 0.1s of EOF
# ("me_thread_encoder_init failed" / "Could not open encoder before EOF").
EOF_MARGIN_S = 0.25


def clamp_timestamp(timestamp: float, duration: float, margin: float = EOF_MARGIN_S) -> float:
    """Keep a seek off the end of the file.

    A timestamp inside the last ``margin`` seconds, or past the end, becomes
    ``duration - margin`` (or 0 when the file is shorter than the margin).
    """
    timestamp = max(0.0, float(timestamp))
    if duration <= 0:
        return 0.0
    latest = max(0.0, float(duration) - float(margin))
    if timestamp > latest:
        return latest
    return timestamp


def seek_candidates(timestamp: float, duration: float | None = None) -> list[float]:
    """Clamped seek, then earlier times, then the first frame."""
    ts = max(0.0, float(timestamp))
    if duration is not None and duration > 0:
        ts = clamp_timestamp(ts, duration)
    raw = [ts, max(0.0, ts - 0.5), max(0.0, ts - 1.0), 0.0]
    out: list[float] = []
    for value in raw:
        rounded = round(value, 3)
        if rounded not in out:
            out.append(rounded)
    return out


def grab_frame(video: Path, timestamp: float, dest: Path, *, duration: float | None = None) -> None:
    """Write one JPEG. Seeks near EOF are clamped, then stepped back until a frame decodes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors: list[MediaError] = []
    for ts in seek_candidates(timestamp, duration):
        dest.unlink(missing_ok=True)
        try:
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{ts:.3f}",
                    "-i",
                    str(video),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    str(dest),
                ]
            )
        except MediaError as exc:
            errors.append(exc)
            continue
        if dest.exists() and dest.stat().st_size > 0:
            return
        errors.append(MediaError(f"ffmpeg wrote no frame at {ts:.3f}"))
    where = f"{float(timestamp):.3f}"
    if duration is not None:
        where += f" (duration {float(duration):.3f})"
    detail = errors[-1] if errors else "no seek candidates"
    raise MediaError(f"no decodable frame at {where}: {detail}")
