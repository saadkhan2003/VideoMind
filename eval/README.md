# Evaluation

## Hit rule

A retrieved segment is a hit when it **contains the midpoint of a labeled relevant span**. If several overlapping segments cover the same span, only the first one in the ranking gets credit. That keeps nDCG at or below 1.

Recall@k is 1 when any of the top k segments is a hit. MRR@10 is the reciprocal rank of the first hit inside the top 10. nDCG@10 uses binary gain and log base 2.

## File format

One JSON object per line:

```json
{"query_id":"q1","query":"where is backpropagation explained","type":"spoken","video_id":"sample-lecture","relevant_spans":[[8,16]],"split":"test"}
```

- `type` is `spoken`, `visual`, or `keyword`.
- `split` is `dev` (tune on this) or `test` (report on this).
- `relevant_spans` is a list of `[start_s, end_s]` pairs.

`eval/queries.sample.jsonl` is a four-query example tied to the synthetic clip. It is not a 150-query labeled set. Build that yourself with the videos you have rights to use.

## Commands

```bash
python eval/label_tool.py validate eval/queries.sample.jsonl
python eval/label_tool.py add eval/queries.jsonl \
  --id q10 --query "when is the bar chart shown" --type visual \
  --video my-lecture --start 120 --end 150 --split dev
python eval/run_eval.py --queries eval/queries.jsonl --split test --ablation all --out eval/results/sample
```

The runner prints Recall@1/5/10, MRR@10, and nDCG@10 overall and by query type. Do not paste a sample-clip run into the README table.
