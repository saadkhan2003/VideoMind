# Cloud run (Saad's machine)

This run uses your own keys. Nothing in this file calls a paid API. The commands below are what you run on a plain Linux box: CPU only, Python 3, [uv](https://docs.astral.sh/uv/), ffmpeg. No GPU.

The pipeline reads these variables and nothing is hardcoded:

| Variable | What it is |
|---|---|
| `OPENROUTER_API_KEY` | Captions. `OPENROUTER_VLM_MODEL=auto` picks the cheapest capable vision model from the live catalog (`GET https://openrouter.ai/api/v1/models`, which is not billed). |
| `QDRANT_URL` | Qdrant Cloud cluster URL, for example `https://<id>.<region>.cloud.qdrant.io`. If the URL has no port, the client uses **443**. |
| `QDRANT_API_KEY` | Qdrant Cloud API key. |
| `R2_ACCOUNT_ID` | Cloudflare account id. The S3 endpoint becomes `https://<id>.r2.cloudflarestorage.com`. |
| `R2_ACCESS_KEY_ID` | R2 access key id. |
| `R2_SECRET_ACCESS_KEY` | R2 secret. |
| `R2_BUCKET` | Bucket name. Default `videomind-media` if unset. |
| `LANGFUSE_PUBLIC_KEY` | Langfuse Cloud public key. |
| `LANGFUSE_SECRET_KEY` | Langfuse Cloud secret key. |
| `LANGFUSE_HOST` | Default `https://cloud.langfuse.com`. |

`--max-usd` (default **0.15**) stops further caption calls once the sum of OpenRouter `usage.cost` reaches that amount. Cache hits add nothing. If a response omits `usage.cost`, the call is priced from the reported token counts times the catalog's per-token price for the model that was selected. One in-flight call can finish slightly over the cap; the next frame is not sent.

## Clips

Downloaded by the script. They are not in git.

| id | File | License | Credit |
|---|---|---|---|
| `edison-1920s` | [Edison speech, 1920s.ogv](https://commons.wikimedia.org/wiki/File:Edison_speech,_1920s.ogv) (~130 s, public domain) | Public domain | Wikimedia Commons |
| `hufsky-data-retention` | [Demonstration data retention speech, part 1](https://commons.wikimedia.org/wiki/File:Demonstration_data_retention_at_BMVIT_speech_Hufsky_1_2007-06-07.ogv) (~30 s) | CC BY-SA 3.0 | Florian Prischl |
| `talking-tree-2011` | [Talking tree 2011.webm](https://commons.wikimedia.org/wiki/File:Talking_tree_2011.webm) (~47 s) | CC BY 2.0 | Louise McLaren |

`eval/queries.cloud.jsonl` has four queries. The spans were taken from a faster-whisper `tiny` pass on these exact files (10 Nov 2026): "experiment" and "memorandum" in the Edison recording, "Christmas is coming" and "trees in the royal parks" in the talking-tree recording. The Hufsky clip is ingested and not labeled: on that same tiny model the transcript was not usable English, so no span was invented for it. If your transcript does not contain those words, fix the spans with `eval/label_tool.py` before you trust the numbers. Do not copy the scores into the README table until you have looked at them.

## Commands

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg ca-certificates curl
curl -LsSf https://astral.sh/uv/install.sh | sh
# open a new shell so uv is on PATH, or: source "$HOME/.local/bin/env"

cd /path/to/videomind
uv venv --python 3.12
uv pip install -r requirements.txt

cp .env.example .env
chmod 600 .env
# Put the keys in .env. Do not commit it.
set -a
source .env
set +a

# Confirms the variables are set and prints the model the live price list selected.
# This GET is free. It does not download video and it does not send an image.
.venv/bin/python scripts/cloud_ingest.py --dry-run

# Index the three clips. CPU Whisper (tiny unless WHISPER_MODEL is set).
# Caption calls stop at $0.15 of reported OpenRouter usage.
.venv/bin/python scripts/cloud_ingest.py --max-usd 0.15

# Retrieval numbers for the labeled queries. Writes JSON and Markdown under eval/results/cloud.
# These are this run only.
.venv/bin/python eval/run_eval.py \
  --queries eval/queries.cloud.jsonl \
  --split test \
  --ablation all \
  --out eval/results/cloud
```

Optional: include the one `dev` query as well.

```bash
.venv/bin/python eval/run_eval.py \
  --queries eval/queries.cloud.jsonl \
  --split all \
  --ablation hybrid_rerank \
  --out eval/results/cloud
```

To add a span after you listen to the Hufsky clip:

```bash
.venv/bin/python eval/label_tool.py add eval/queries.cloud.jsonl \
  --id hufsky-1 \
  --query "the phrase you actually heard" \
  --type spoken \
  --video hufsky-data-retention \
  --start 0 \
  --end 10 \
  --split dev
```

Replace the start and end with the seconds you marked. A hit is a segment that contains the midpoint of that span.

## What the script changes for these short files

`scripts/cloud_ingest.py` forces `CAPTION_BACKEND=openrouter`, sets the budget from `--max-usd`, and uses 20-second chunks with 5 seconds of overlap so a two-minute recording is more than one segment. ASR stays on CPU (`WHISPER_DEVICE` is set to `cpu` by the script). The default model size is whatever `WHISPER_MODEL` says, or `tiny` when that variable is empty.

Langfuse receives each caption call when both keys are set. A copy is also appended to `$DATA_DIR/traces.jsonl`.

## If you only want to see the bill before it grows

The dry run prints a catalog estimate per caption. That estimate is 800 prompt tokens plus 150 completion tokens at the published per-token price. On 10 Nov 2026 the same rules, against the live catalog, selected `qwen/qwen3.7-flash` at about $0.000044 per caption. Your dry run prints the id the catalog returns that day. The guard does not use the estimate. It uses `usage.cost` from each completed response. With a $0.15 cap and a model around a few hundredths of a cent per frame, a handful of keyframes on these three clips stays inside the cap unless the catalog has moved a long way. Watch the log line `cost_usd=` at the end of the caption stage.
