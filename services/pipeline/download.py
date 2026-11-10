"""HTTP download with a Wikimedia-compatible User-Agent and retry."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

log = logging.getLogger("videomind.download")

# https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
# A descriptive agent with a contact URL. The default httpx agent is blocked (HTTP 403).
USER_AGENT = "VideoMind/0.1 (portfolio project; https://github.com/saadkhan2003)"

RETRY_STATUS = frozenset({403, 408, 429, 500, 502, 503, 504})


def download_file(
    url: str,
    dest: Path,
    *,
    attempts: int = 4,
    backoff_s: float = 0.5,
    sleep=time.sleep,
    client: httpx.Client | None = None,
) -> None:
    """Stream ``url`` to ``dest``. Retries 403, 429, and 5xx with exponential backoff.

    The body is written to a sibling ``.part`` file and renamed only after a
    complete 2xx response, so a failed attempt cannot look like a finished download.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    own_client = client is None
    if client is None:
        client = httpx.Client(follow_redirects=True, timeout=120.0)
    try:
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                _one_attempt(client, url, dest, partial)
                return
            except httpx.HTTPStatusError as exc:
                last = exc
                code = exc.response.status_code
                if code not in RETRY_STATUS or attempt == attempts:
                    raise
                _warn_retry(url, attempt, attempts, f"HTTP {code}")
            except httpx.TransportError as exc:
                last = exc
                if attempt == attempts:
                    raise
                _warn_retry(url, attempt, attempts, str(exc))
            sleep(backoff_s * (2 ** (attempt - 1)))
        if last is not None:
            raise last
    finally:
        partial.unlink(missing_ok=True)
        if own_client:
            client.close()


def _warn_retry(url: str, attempt: int, attempts: int, detail: str) -> None:
    log.warning("download %s failed (%s) on attempt %s/%s; retrying", url, detail, attempt, attempts)


def _one_attempt(client: httpx.Client, url: str, dest: Path, partial: Path) -> None:
    headers = {"User-Agent": USER_AGENT}
    with client.stream("GET", url, headers=headers) as response:
        if response.status_code in RETRY_STATUS:
            response.read()
            raise httpx.HTTPStatusError(
                f"HTTP {response.status_code} for {url}",
                request=response.request,
                response=response,
            )
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    partial.replace(dest)
