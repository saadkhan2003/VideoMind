from __future__ import annotations

import threading
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.time()
        with self._lock:
            window = [stamp for stamp in self.hits[key] if now - stamp < 60]
            if len(window) >= self.per_minute:
                self.hits[key] = window
                return False
            window.append(now)
            self.hits[key] = window
            return True
