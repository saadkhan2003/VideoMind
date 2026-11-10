from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from pipeline.types import AsrSegment, Transcript, Word

log = logging.getLogger("videomind.asr")
_models: dict[tuple[str, str, str], object] = {}
_lock = threading.Lock()
_av_patched = False


def _compat_pyav() -> None:
    """faster-whisper passes metadata_errors= to av.open. PyAV 19 dropped that argument.

    av.open is a builtin, so inspect.signature cannot see its parameters.
    Dropping the keyword is safe: older PyAV treats it as optional.
    """
    global _av_patched
    if _av_patched:
        return
    import av

    original = av.open

    def open_compat(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return original(*args, **kwargs)

    av.open = open_compat
    _av_patched = True


def get_whisper(model_size: str, device: str, compute_type: str):
    key = (model_size, device, compute_type)
    with _lock:
        if key not in _models:
            from faster_whisper import WhisperModel

            log.info("loading faster-whisper %s (%s/%s)", model_size, device, compute_type)
            _models[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
        return _models[key]


def transcribe_file(
    wav_path: str | Path,
    *,
    model_size: str = "tiny",
    device: str = "cpu",
    compute_type: str = "int8",
    vad_filter: bool = True,
) -> Transcript:
    model = get_whisper(model_size, device, compute_type)
    _compat_pyav()
    started = time.perf_counter()
    segments_iter, info = model.transcribe(
        str(wav_path),
        vad_filter=vad_filter,
        word_timestamps=True,
    )
    segments: list[AsrSegment] = []
    for segment in segments_iter:
        words = []
        for word in segment.words or []:
            words.append(Word(word=word.word, start=float(word.start), end=float(word.end)))
        segments.append(
            AsrSegment(
                start=float(segment.start),
                end=float(segment.end),
                text=(segment.text or "").strip(),
                words=words,
            )
        )
    elapsed = time.perf_counter() - started
    duration = float(getattr(info, "duration", 0.0) or 0.0)
    if duration <= 0 and segments:
        duration = segments[-1].end
    rtf = elapsed / duration if duration > 0 else 0.0
    log.info(
        "asr model=%s duration=%.2fs elapsed=%.2fs rtf=%.3f segments=%d",
        model_size,
        duration,
        elapsed,
        rtf,
        len(segments),
    )
    return Transcript(
        language=getattr(info, "language", "") or "",
        duration=duration,
        rtf=rtf,
        segments=segments,
    )
