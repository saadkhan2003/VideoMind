#!/usr/bin/env bash
# Install only inside GitHub Codespaces, never on the user's laptop.
set -euo pipefail

if [[ "${CODESPACES:-}" != "true" ]]; then
  echo "Refusing installation outside GitHub Codespaces." >&2
  exit 1
fi

cd "$(dirname "$0")/.."
sudo apt-get update
sudo apt-get install -y --no-install-recommends ffmpeg espeak-ng tesseract-ocr

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
npm --prefix services/web ci

echo "Cloud dependencies ready. No model weights downloaded or paid APIs called."
echo "See docs/codespaces.md for checks and the optional sample demo."
