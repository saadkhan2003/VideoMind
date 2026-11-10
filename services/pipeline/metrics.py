from prometheus_client import Counter, Gauge, Histogram

JOBS = Gauge("videomind_jobs", "Jobs by state", ["state"])
QUEUE_DEPTH = Gauge("videomind_queue_depth", "Jobs waiting in the queue")
STAGE_DURATION = Histogram(
    "videomind_stage_duration_seconds",
    "Ingestion stage duration in seconds",
    ["stage"],
    buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600, 1800),
)
SEARCH_STAGE = Histogram(
    "videomind_search_stage_duration_seconds",
    "Search latency by stage",
    ["stage"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
HTTP_LATENCY = Histogram(
    "videomind_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
VLM_COST = Counter(
    "videomind_vlm_cost_usd_total",
    "Reported model cost in USD",
    ["model"],
)
JOB_FAILURES = Counter("videomind_job_failures_total", "Jobs that ended failed")
VLM_CALLS = Counter(
    "videomind_vlm_calls_total",
    "Caption and answer model calls",
    ["model", "cache"],
)


def refresh_job_gauges(counts: dict[str, int]) -> None:
    for state in ("queued", "processing", "indexed", "failed"):
        JOBS.labels(state=state).set(counts.get(state, 0))
    QUEUE_DEPTH.set(counts.get("queued", 0))
