# Evaluation

## Hit rule

A retrieved segment is a hit when it **contains the midpoint of a labeled relevant span**. If several overlapping segments cover the same span, only the first one in the ranking gets credit. The gain is the span's grade. A span without a grade counts as 1, which is the old binary label. Grade 2 is an exact mention. Grade 1 is a partial or later mention. nDCG uses those gains (log base 2) and the ideal ranking is the grades sorted high to low.

Recall@k is 1 when any of the top k segments is a hit. MRR@10 is the reciprocal rank of the first hit inside the top 10.

A `negative` query has no relevant span. It is a hard negative (the clip does not contain the thing). Those queries are listed and left out of the averages, because the retriever always returns neighbors.

## File format

One JSON object per line:

```json
{"query_id":"q1","query":"where is backpropagation explained","type":"spoken","video_id":"sample-lecture","relevant_spans":[[8,16,2]],"split":"test"}
```

- `type` is `spoken`, `visual`, `keyword`, or `negative`.
- `split` is `dev` (tune on this) or `test` (report on this).
- `relevant_spans` is a list of `[start_s, end_s]` or `[start_s, end_s, grade]` with grade 1 or 2. A negative query uses `[]`.

`eval/queries.sample.jsonl` is a four-query example tied to the synthetic clip. `eval/queries.cloud.jsonl` is the graded set for the three cloud clips. `eval/queries.cloud.spec.jsonl` is what `eval/align_labels.py` reads so you can rebuild those spans from your own transcript and captions. Neither file is a 150-query labeled set.

## Commands

Both forms work from the repo root. `python eval/run_eval.py` used to fail with `ModuleNotFoundError: No module named 'eval'` because the script directory hid the package. The script now puts the repo root on `sys.path` first.

```bash
python -m eval.run_eval --queries eval/queries.jsonl --split test --ablation all --out eval/results/sample
python eval/run_eval.py --queries eval/queries.jsonl --split test --ablation all --out eval/results/sample

python -m eval.label_tool validate eval/queries.sample.jsonl
python eval/label_tool.py add eval/queries.jsonl \
  --id q10 --query "when is the bar chart shown" --type visual \
  --video my-lecture --start 120 --end 150 --grade 2 --split dev

python -m eval.align_labels \
  --spec eval/queries.cloud.spec.jsonl \
  --transcripts "$DATA_DIR" \
  --db "$DATA_DIR/videomind.db" \
  --from-store \
  --out eval/queries.cloud.jsonl
```

`align_labels` reads transcript JSON and segment rows you already stored. It does not call OpenRouter. A missing phrase warns and keeps the previous spans. `--strict` exits instead. See `CLOUD_RUN.md` for the cloud paths. The runner prints Recall@1/5/10, MRR@10, and nDCG@10 overall and by query type. The README table is the 10 Nov 2026 measurement. Do not paste a sample-clip run over it.
