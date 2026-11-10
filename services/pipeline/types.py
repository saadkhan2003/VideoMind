from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Word:
    word: str
    start: float
    end: float


@dataclass
class AsrSegment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    language: str
    duration: float
    rtf: float
    segments: list[AsrSegment]

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "duration": self.duration,
            "rtf": self.rtf,
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "words": [asdict(w) for w in s.words],
                }
                for s in self.segments
            ],
        }


@dataclass
class Keyframe:
    time: float
    image_path: str
    thumb_path: str
    image_hash: str
    image_key: str = ""
    thumb_key: str = ""
    caption: str = ""
    ocr_text: str = ""
    caption_backend: str = ""
    caption_model: str = ""
    cache_hit: bool = False
    cost_usd: float = 0.0


@dataclass
class Chunk:
    start: float
    end: float
    transcript_text: str
    visual_caption: str = ""
    ocr_text: str = ""
    keyframe_key: str = ""
    keyframe_time: float | None = None


def format_ts(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
