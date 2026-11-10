"""Build a short synthetic lecture with espeak-ng and ffmpeg.

Four 8-second slides. The speech and the burned-in title match, so a search
for the slide title can land on that window after ASR and OCR.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

SLIDES = [
    {
        "title": "Neural Networks",
        "speech": "Welcome to the lecture on neural networks.",
        "bg": "0x1B3A4B",
        "fg": "white",
    },
    {
        "title": "Backpropagation",
        "speech": "In this section we explain backpropagation. The gradient flows backward through each layer.",
        "bg": "0xF4F0E6",
        "fg": "black",
    },
    {
        "title": "Architecture Diagram",
        "speech": "Here is the architecture diagram on the slide.",
        "bg": "white",
        "fg": "black",
    },
    {
        "title": "Loss Function",
        "speech": "The loss function is mean squared error.",
        "bg": "0x1B3A4B",
        "fg": "white",
    },
]

SLIDE_SECONDS = 8


def generate_lecture(dest: Path, work: Path | None = None) -> Path:
    dest = Path(dest)
    work = Path(work) if work else dest.parent / "sample_build"
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for index, slide in enumerate(SLIDES):
        part = work / f"slide_{index}.mp4"
        _render_slide(work / f"s{index}", slide, part)
        parts.append(part)
    listing = work / "list.txt"
    listing.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in parts),
        encoding="utf-8",
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


def _render_slide(tmp: Path, slide: dict, dest: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    speech = tmp / "speech.wav"
    padded = tmp / "padded.wav"
    label = tmp / "label.txt"
    label.write_text(slide["title"], encoding="utf-8")
    subprocess.run(
        ["espeak-ng", "-s", "125", "-w", str(speech), slide["speech"]],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(speech),
            "-af",
            f"apad=whole_dur={SLIDE_SECONDS}",
            "-t",
            str(SLIDE_SECONDS),
            str(padded),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={slide['bg']}:s=1280x720:d={SLIDE_SECONDS}",
            "-i",
            str(padded),
            "-vf",
            (
                f"drawtext=fontfile={FONT}:textfile={label}:fontsize=64:"
                f"fontcolor={slide['fg']}:x=(w-text_w)/2:y=(h-text_h)/2"
            ),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            str(SLIDE_SECONDS),
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
