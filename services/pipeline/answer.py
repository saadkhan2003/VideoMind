from __future__ import annotations

import time

from pipeline.config import Settings
from pipeline.embed import tokenize
from pipeline.retrieve import Hit
from pipeline.tracing import Tracer
from pipeline.types import format_ts


def _grounded(query: str, hit: Hit) -> bool:
    q_tokens = set(tokenize(query))
    text = " ".join(
        part for part in (hit.transcript_text, hit.visual_caption, hit.ocr_text) if part
    )
    return bool(q_tokens and q_tokens & set(tokenize(text)))


def extractive_answer(query: str, hits: list[Hit], min_score: float) -> dict:
    if not hits or hits[0].score < min_score or not _grounded(query, hits[0]):
        return {
            "refused": True,
            "answer": "The indexed moments do not contain an answer to that question.",
            "citations": [],
        }
    chosen = hits[:5]
    lines = []
    citations = []
    for hit in chosen:
        text = (hit.transcript_text or hit.visual_caption or hit.ocr_text).strip()
        if not text:
            continue
        stamp = format_ts(hit.start_s)
        lines.append(f"{text} [{hit.title} {stamp}]")
        citations.append(_citation(hit))
        break
    if not citations:
        return {
            "refused": True,
            "answer": "The indexed moments do not contain an answer to that question.",
            "citations": [],
        }
    return {"refused": False, "answer": lines[0], "citations": citations}


def _citation(hit: Hit) -> dict:
    return {
        "video_id": hit.video_id,
        "segment_id": hit.segment_id,
        "title": hit.title,
        "start_s": hit.start_s,
        "end_s": hit.end_s,
        "timestamp": format_ts(hit.start_s),
    }


def llm_answer(query: str, hits: list[Hit], settings: Settings, tracer: Tracer) -> dict:
    import httpx

    context_lines = []
    allowed = {}
    for hit in hits[:5]:
        stamp = format_ts(hit.start_s)
        allowed[hit.segment_id] = hit
        body = (hit.transcript_text or hit.visual_caption or hit.ocr_text).strip()
        context_lines.append(
            f"[{hit.segment_id} | {hit.title} | {stamp}] {body}"
        )
    prompt = (
        "Answer the question using only the moments below. "
        "Cite segment ids that support the answer, as a JSON object "
        '{"answer": "...", "segment_ids": ["..."]}. '
        "If the moments do not contain the answer, return "
        '{"answer": "", "segment_ids": []}.\n\n'
        f"Question: {query}\n\nMoments:\n" + "\n".join(context_lines)
    )
    started = time.perf_counter()
    response = httpx.post(
        f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://github.com/videomind",
            "X-Title": "VideoMind",
        },
        json={
            "model": settings.openrouter_answer_model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    latency = time.perf_counter() - started
    usage = body.get("usage") or {}
    cost = float(usage.get("cost") or 0.0)
    tracer.record(
        name="answer",
        model=settings.openrouter_answer_model,
        input={"query": query, "segments": list(allowed)},
        output=content,
        latency_s=latency,
        cost_usd=cost,
        metadata={"backend": "openrouter"},
    )
    import json

    text = str(content).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return extractive_answer(query, hits, settings.answer_min_score)
    ids = [str(item) for item in parsed.get("segment_ids") or []]
    citations = [_citation(allowed[sid]) for sid in ids if sid in allowed]
    answer = str(parsed.get("answer") or "").strip()
    if not answer or not citations:
        return {
            "refused": True,
            "answer": "The indexed moments do not contain an answer to that question.",
            "citations": [],
        }
    return {"refused": False, "answer": answer, "citations": citations}


def answer_question(
    query: str,
    hits: list[Hit],
    settings: Settings,
    tracer: Tracer,
) -> dict:
    if settings.openrouter_api_key:
        try:
            return llm_answer(query, hits, settings, tracer)
        except Exception:
            # A failed model call must not invent an answer. Fall through to extractive.
            pass
    result = extractive_answer(query, hits, settings.answer_min_score)
    tracer.record(
        name="answer",
        model="extractive",
        input={"query": query},
        output=result["answer"],
        latency_s=0.0,
        cost_usd=0.0,
        metadata={"refused": result["refused"]},
    )
    return result
