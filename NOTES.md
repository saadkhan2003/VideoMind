# Notes

Engineering choices made while building the first slice. The interview section at the bottom is blank on purpose.

## Why the defaults are small

The interesting path (hybrid search, timestamped playback, eval metrics, a chart, a pipeline) had to run on a CPU laptop with no API key. That forced a few stand-ins:

- **Hashing embedder** instead of `BAAI/bge-m3`. Same interface, no download. Shared tokens raise cosine similarity, which is enough to test fusion. It will not match a paraphrase. Switching backend is one environment variable plus a new collection, because bge-m3 is 1024-d and the hash default is 384-d.
- **Lexical reranker** instead of loading `bge-reranker-v2-m3` at startup. `CrossEncoderReranker` still constructs `sentence_transformers.CrossEncoder` with that model name when you ask for it. The unit test injects a fake `predict` so the call shape is locked without the weights.
- **Tesseract** as a caption backend. It reads burned-in titles on the synthetic slides. OpenRouter and vLLM (OpenAI-compatible `/chat/completions`, image as a data URL, Qwen2.5-VL model name from the environment) are the two backends the plan asked for. Both are behind the same `caption()` method and the same hash cache.
- **Embedded Qdrant** (`QdrantClient(":memory:")` in tests, a path on disk for the demo). Named vectors `text_dense`, `visual_dense`, and sparse `sparse` with the IDF modifier. Hybrid search uses `query_points` prefetch + `Fusion.RRF`, and falls back to an in-process RRF if that call throws. A server URL is required before Ray workers can share the index; two processes cannot open the same embedded path.
- **SQLite** unless `DATABASE_URL` is Postgres. The models are plain SQLAlchemy so either works. Jobs move `queued → processing → indexed | failed`, and a failed job can return to `queued`.

## Chunking

Windows are about 45 seconds, overlap about 10, hard cap 60, ends snapped to Whisper segment boundaries. If the remainder of the video fits under the cap, the last window closes on the duration so there is no gap. The sample clip is 32 seconds, so the ingest script drops the window to 8 seconds. Otherwise the whole clip would be one segment and the player would start at 0, which hides the point of the project.

## Hit rule

A segment hits a label when it contains the midpoint of a relevant span. Each span pays out once, to the earliest segment that covers it. Recall@k is "did any hit appear". That matches "jump to the moment" better than requiring a 50 percent overlap, and it is what `eval/metrics.py` tests against hand-computed nDCG.

## Workers

The pipeline function is the same for every backend. Inline mode runs it on a thread in the API process (or in the request when `EAGER_JOBS=1`, which the tests use). `poll` claims a queued row and runs it. Celery wraps that function with retries and separate `cpu` and `gpu` queues. Ray exposes the same body as a remote with `max_retries=2`, and a helper that runs ASR and scene detection as two remotes. Stage-level retries with backoff are inside the pipeline, covered by a test that fails twice and then succeeds. Killing a real worker process was not done here.

## What was verified in this environment

- `pytest` unit and integration tests, including upload limits, job transitions, hybrid search on an in-memory Qdrant, caption cache hits, and a perceptual-hash dedup on a static ffmpeg clip.
- `pytest -m e2e`: espeak-ng + ffmpeg lecture, faster-whisper tiny on CPU, PySceneDetect, Tesseract, index, search for a word that the ASR actually emitted, and a hit whose window covers that word's timestamp.
- `npm run build` for the Next.js app.
- `helm lint` and `terraform validate` (providers downloaded, no apply).

Docker Compose was not started in the build environment. No GPU and no k3s cluster were used here.

A later run on another machine, with keys, measured the three-clip test split on 10 Nov 2026. The README headline is `bge-m3` plus `bge-reranker-v2-m3` on CPU (22 scored queries, collection `segments_bge`). The hash embedder is the smaller comparison table. Caption spend across both ingest runs was $0.0020 on `qwen/qwen3.7-flash`. The reranker stays off unless you turn it on. The Hetzner VM and the k3s install are still yours to do.

## Interview prompts

Write the answers yourself before you put VideoMind on a CV. A short paragraph each is enough. If you cannot write it, take the bullet off the CV.

1. What does Whisper's VAD filter change, and what is a real-time factor?
2. Why pick keyframes with a scene detector instead of one frame every N seconds?
3. How can a VLM caption be wrong, and how would you catch it?
4. When does BM25 beat a dense embedding, and what is the RRF formula you implemented?
5. Why rerank only the top 50 with a cross-encoder?
6. Compute Recall@k, MRR, and nDCG by hand for a three-document ranking. The unit test in `eval/tests/test_metrics.py` is the worked example.
7. What happens to timestamp precision if you widen the chunk window?
8. How is a Ray task different from a Celery task, in this repo's code?
9. What does the Helm chart add that the Docker Compose file does not?
10. Why is Terraform state not in git, and where would you put it?
11. Which alert in `monitoring/alerts.yml` would you actually wake up for?
