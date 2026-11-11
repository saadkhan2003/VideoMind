# Work in GitHub Codespaces

Use Codespaces for installs, builds, and the CPU demo. Keep the laptop copy as
source and backup only. Codespaces is a development environment, not an always-on
production host; compute and storage count against your GitHub quota.

## Setup

New Codespaces use `.devcontainer/devcontainer.json`: Python 3.12, Node 22, SSH,
ffmpeg, espeak-ng, Tesseract, and project dependencies. Setup does **not** download
Whisper/BGE weights, ingest videos, or call paid APIs.

For a Codespace created before this configuration, run this **in its terminal**:

```bash
bash .devcontainer/setup.sh
```

Alternatively, use **Codespaces: Rebuild Container**. Back up any uncommitted
source work first. Do not run setup or the following commands on your laptop.

## Check the recovered code

```bash
make lint
make test
npm --prefix services/web run build
```

The optional end-to-end check downloads the tiny Whisper model **inside the
Codespace** and runs the generated clip through ASR, OCR, indexing, and search:

```bash
make e2e
```

## Run the no-paid-API demo

```bash
bash scripts/demo.sh
make api
```

In a second Codespace terminal:

```bash
make web
```

Open port **43123** from the Codespaces **Ports** panel. The frontend proxies API
requests to port 43124 internally. Keep both ports **Private**: this demo is not
hardened for unauthenticated public hosting. Search `architecture diagram`, then
play the matching moment.

Stop the API before re-running ingestion: embedded Qdrant cannot be opened by
both processes at once. The demo uses Tesseract, hash embeddings, and local
storage inside the Codespace. It does not reproduce the historical BGE/cloud
metrics in the README.

## Secrets and quota

- No secrets are needed for the sample demo. Do not create `.env` from real keys
  just to run it.
- For later cloud integrations, use repository-selected **Codespaces secrets**
  in GitHub settings. Do not commit keys or print environment variables.
- Real OpenRouter calls require a separately approved spending limit. Adding
  secrets is not approval to spend.
- Keep the 15-minute idle timeout. Stop the Codespace from GitHub when finished;
  an open demo tab can keep it active. Stopped Codespaces still use storage.
- Keep source commits pushed. Downloaded media, model caches, and `.env` are not
  protected by a Git push; copy any irreplaceable artifacts to approved storage
  before deleting a Codespace.
