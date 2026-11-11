# Codespaces recovery verification

Date: 11 November 2026. Recovered starting commit: `48fc81dc`.

## Executed in GitHub Codespaces

- Installed `requirements.txt` in the cloud virtual environment, plus FFmpeg,
  espeak-ng, and Tesseract in the cloud container.
- `ruff check services eval scripts`: passed.
- `pytest -q`: **53 passed, 1 deselected**.
- `pytest -q -m e2e`: **1 passed, 53 deselected**, using the actual tiny Whisper
  model, generated video, OCR, index, and timestamp-aware retrieval.
- `npm ci` and `npm run build` in `services/web`: passed, including TypeScript.
- `npm run lint` in `services/web`: passed.
- `docker compose -f deploy/docker-compose.yml config --quiet`: passed. This
  validates the configuration only; the Compose services were not started.
- `bash scripts/demo.sh`: indexed the generated lecture and returned hits for
  the three sample searches without paid API calls.
- HTTP checks: web page, proxied `/backend/healthz`, and proxied search returned
  200. Health reported working SQLite, embedded Qdrant, and cloud-local storage.
- Browser check through an SSH-forwarded port: searched `architecture diagram`,
  clicked the first **Play this moment**, and confirmed loaded video playback
  with media fragment `#t=16.29,26.82`, duration about 32 seconds, and no video
  error.

The initial five integration-test failures were missing-FFmpeg errors, not
application regressions. All five passed after installing FFmpeg.

## Boundaries

These checks used the initial Codespaces image's Python 3.14 and the installed
Node runtime. The new devcontainer declares Python 3.12 and Node 22 for
reproducibility, but a rebuild of that image has not yet been verified. Its JSON,
shell syntax, and refusal to install outside Codespaces were checked separately.

This is a **private, temporary development demo**, using Tesseract captions,
hash embeddings, SQLite, and embedded Qdrant. It is not a reproduction of the
historical three-clip BGE benchmark, not a new quality/latency benchmark, and not
a production deployment. Ports 43123 and 43124 are private. The Codespace has a
15-minute idle timeout and consumes the owner's compute and storage quota.

Still unverified in this recovery: Docker image builds and a running Compose
stack, Kubernetes deployment, live R2/Qdrant Cloud/Langfuse integration with new
credentials, broader labeled-corpus evaluation, and a recorded walkthrough.
No paid APIs or paid infrastructure were invoked.

See [codespaces.md](codespaces.md) for restarting the demo safely. Store any
future API keys in repository-selected Codespaces secrets; never commit `.env`.
