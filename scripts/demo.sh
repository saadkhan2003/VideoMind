#!/usr/bin/env bash
# CPU demo: synthetic lecture, index, three searches.
# Forces the local stack so a .env full of cloud keys is not used.
# Does not call OpenRouter or any other paid API.

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

export CAPTION_BACKEND=tesseract
export EMBEDDING_BACKEND=hash
export RERANKER_BACKEND=lexical
export OPENROUTER_API_KEY=
export QDRANT_URL=
export QDRANT_API_KEY=
export DATABASE_URL="${DEMO_DATABASE_URL:-sqlite:///./data/videomind.db}"
export DATA_DIR="${DEMO_DATA_DIR:-./data}"

echo "Indexing the synthetic lecture and running three searches."
echo "If Qdrant reports a lock, stop the API that already has ${DATA_DIR}/qdrant open."
PYTHONPATH=services .venv/bin/python scripts/ingest_sample.py
echo
echo "From another shell: make api    then    make web"
echo "Open http://127.0.0.1:43123 and search backpropagation, architecture diagram, or loss function."
