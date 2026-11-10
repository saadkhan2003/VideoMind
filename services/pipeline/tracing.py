from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from pipeline.config import Settings
from pipeline.metrics import VLM_CALLS, VLM_COST

log = logging.getLogger("videomind.trace")


class Tracer:
    """Always writes a local JSONL trace. Forwards to Langfuse when keys are set."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = Path(settings.data_dir) / "traces.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._langfuse = None
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            try:
                from langfuse import Langfuse

                self._langfuse = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Langfuse client unavailable: %s", exc)

    def record(
        self,
        *,
        name: str,
        model: str,
        input: Any,
        output: Any,
        latency_s: float,
        cost_usd: float = 0.0,
        metadata: dict | None = None,
        cache_hit: bool = False,
    ) -> dict:
        record = {
            "name": name,
            "model": model,
            "input": input,
            "output": output,
            "latency_s": latency_s,
            "cost_usd": cost_usd,
            "cache_hit": cache_hit,
            "metadata": metadata or {},
            "ts": time.time(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        VLM_CALLS.labels(model=model or "unknown", cache="hit" if cache_hit else "miss").inc()
        if cost_usd:
            VLM_COST.labels(model=model or "unknown").inc(cost_usd)
        if self._langfuse is not None and not cache_hit:
            self._export_langfuse(
                name=name,
                model=model,
                input=input,
                output=output,
                cost_usd=cost_usd,
                metadata=metadata,
            )
        return record

    def _export_langfuse(
        self,
        *,
        name: str,
        model: str,
        input: Any,
        output: Any,
        cost_usd: float,
        metadata: dict | None,
    ) -> None:
        """langfuse 5.2 has start_observation, not start_generation.

        A failure here is a warning. The JSONL line is already written, and the
        ingest job keeps going.
        """
        client = self._langfuse
        try:
            kwargs: dict[str, Any] = {
                "as_type": "generation",
                "name": name,
                "input": input,
                "output": output,
                "metadata": metadata or {},
            }
            if model:
                kwargs["model"] = model
            if cost_usd:
                kwargs["cost_details"] = {"total": float(cost_usd)}
            observation = client.start_observation(**kwargs)
            end = getattr(observation, "end", None)
            if end is not None:
                end()
            flush = getattr(client, "flush", None)
            if flush is not None:
                flush()
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Langfuse export failed for %s: %s: %s. The local trace was still written.",
                name,
                type(exc).__name__,
                exc,
            )
