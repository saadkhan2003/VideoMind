from __future__ import annotations

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    segment_id: str
    video_id: str
    title: str
    start_s: float
    end_s: float
    timestamp: str
    end_timestamp: str
    score: float
    snippet: str
    transcript_text: str
    visual_caption: str
    ocr_text: str
    thumbnail_url: str
    lang: str


class SearchResponse(BaseModel):
    query: str
    k: int
    took_ms: float
    hits: list[SearchHit]


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1)
    video_id: str | None = None
    k: int = 5


class Citation(BaseModel):
    video_id: str
    segment_id: str
    title: str
    start_s: float
    end_s: float
    timestamp: str


class AnswerResponse(BaseModel):
    refused: bool
    answer: str
    citations: list[Citation]
