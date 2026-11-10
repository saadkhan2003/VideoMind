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

`eval/queries.cloud.jsonl` has 30 graded queries (spoken, visual, keyword, and four hard negatives) across all three clips. A span is `[start, end]` or `[start, end, grade]`. Grade 2 is the exact phrase or the frame that shows it. Grade 1 is a later or partial mention. Hard negatives have an empty span list and are left out of the Recall / MRR / nDCG averages.

Spoken spans in that file come from one faster-whisper `tiny` pass on these files (word timestamps, VAD on). Tiny does not print the same words on every machine. The Hufsky clip produced no words on that pass, so its labels are visual: the banners readable in the frames (`Freiheit stirbt mit Sicherheit` around 15s, `Demokratie braucht Anonymität` / `STOPPT DATARETENTION` around 28s). Visual spans are the frames that were checked, not a claim about what qwen wrote.

Rerun the labeller against your own transcript and segment rows before you treat the numbers as final. It does not call OpenRouter. `eval/queries.cloud.spec.jsonl` is the input (phrases plus frame fallbacks). The helper rewrites `eval/queries.cloud.jsonl`.

```bash
.venv/bin/python -m eval.align_labels \
  --spec eval/queries.cloud.spec.jsonl \
  --transcripts "$DATA_DIR" \
  --db "$DATA_DIR/videomind.db" \
  --from-store \
  --out eval/queries.cloud.jsonl
```

`--transcripts` reads `$DATA_DIR/objects/videos/<id>/transcript.json` when the object is on local disk. `--from-store` reads the same key from R2 when the R2 variables are set. `--db` is the sqlite file from `DATABASE_URL` (default `./data/videomind.db`) and supplies `visual_caption` and `ocr_text`. If a caption contains the phrase, that segment replaces the frame fallback. If it does not, the helper keeps the frame times and prints a warning.

A spoken phrase that is not in the transcript does not abort the run. The helper warns and keeps the fallback spans or the spans already in `--out`. `--strict` exits on that miss (the old behaviour). A spec line with `on_miss: skip` (the Hufsky speech query) is added only when the transcript actually contains the phrase. `tree-talk` is the phrase `talk and sing` (16.14–17.56s on the cloud tiny-whisper pass).

The 10 Nov 2026 test-split numbers are in the README. They were computed on the committed query file before this phrase fix, so a later eval can move `tree-talk` if you realign first.

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
# These are this run only. Either command works from the repo root.
.venv/bin/python -m eval.run_eval \
  --queries eval/queries.cloud.jsonl \
  --split test \
  --ablation all \
  --out eval/results/cloud

.venv/bin/python eval/run_eval.py \
  --queries eval/queries.cloud.jsonl \
  --split test \
  --ablation all \
  --out eval/results/cloud
```

Optional: include the `dev` queries as well.

```bash
.venv/bin/python -m eval.run_eval \
  --queries eval/queries.cloud.jsonl \
  --split all \
  --ablation hybrid \
  --out eval/results/cloud
```

The printed `n` is the scored queries. The line also reports `hard_negatives`, which are not in the averages. The default ablation is `hybrid` (no reranker). Pass `--ablation hybrid_rerank` only when you want that comparison. `RERANKER_ENABLED` defaults to false for the same reason.

## Rerun when the three clips are already indexed

A file that is already on disk and not empty is not downloaded again. A video whose job is `indexed` is skipped unless you pass `--reindex`. The Hufsky grab at 30.05s of a 30.10s file failed (mjpeg encoder at EOF). Reindex that clip so the seek is clamped and the last frame is captioned. Cached captions cost $0. The new frame is one caption. `--max-usd` still applies.

```bash
set -a
source .env
set +a

.venv/bin/python scripts/cloud_ingest.py --max-usd 0.15 --reindex hufsky-data-retention
```

`--reindex all` runs every clip in the script. Then align (command above) and eval.

To add one span by hand:

```bash
.venv/bin/python -m eval.label_tool add eval/queries.cloud.jsonl \
  --id hufsky-heard \
  --query "the phrase you actually heard" \
  --type spoken \
  --video hufsky-data-retention \
  --start 0 \
  --end 10 \
  --grade 2 \
  --split dev
```

A hit is a segment that contains the midpoint of that span. `--grade` is 1 or 2.

## What the script changes for these short files

`scripts/cloud_ingest.py` forces `CAPTION_BACKEND=openrouter`, sets the budget from `--max-usd`, and uses 20-second chunks with 5 seconds of overlap so a two-minute recording is more than one segment. ASR stays on CPU (`WHISPER_DEVICE` is set to `cpu` by the script). The default model size is whatever `WHISPER_MODEL` says, or `tiny` when that variable is empty.

Downloads send `User-Agent: VideoMind/0.1 (portfolio project; https://github.com/saadkhan2003)` and retry HTTP 403, 429, and 5xx with exponential backoff. Wikimedia rejects the default httpx agent.

Langfuse export uses `start_observation(as_type="generation")` on the pinned `langfuse==5.2.0` client (that release has no `start_generation`). Each caption is also appended to `$DATA_DIR/traces.jsonl`. If the export throws, the log line is `Langfuse export failed for caption: <exception>: <message>. The local trace was still written.` and the job continues.

## If you only want to see the bill before it grows

The dry run prints a catalog estimate per caption. That estimate is 800 prompt tokens plus 150 completion tokens at the published per-token price. On 10 Nov 2026 the same rules, against the live catalog, selected `qwen/qwen3.7-flash` at about $0.000044 per caption. Your dry run prints the id the catalog returns that day. The guard does not use the estimate. It uses `usage.cost` from each completed response. With a $0.15 cap and a model around a few hundredths of a cent per frame, a handful of keyframes on these three clips stays inside the cap unless the catalog has moved a long way. Watch the log line `cost_usd=` at the end of the caption stage.
