# Contributing

VideoMind is in development. Useful contributions include more reliable video
ingestion, reproducible retrieval evaluation, accessible search/playback flows,
and clear deployment boundaries.

## Environment and checks

Use [the Codespaces guide](docs/codespaces.md) for cloud-only development.
`.devcontainer/setup.sh` installs dependencies, not model weights or sample data.
Once the environment is ready:

```bash
make lint
make test
npm --prefix services/web run lint
npm --prefix services/web run build
make e2e
```

The end-to-end check downloads tiny Whisper if not cached. Run it in the cloud
environment, not on a resource-constrained laptop. Unit tests use isolated test
resources; do not point them at a production Qdrant collection or storage bucket.
Read `services/web/AGENTS.md` and the installed Next.js documentation before
changing frontend framework behavior.

## Changes and evidence

For bug fixes, include a regression test and explain the failure being prevented.
For user-facing changes, verify the complete interaction, including a search,
selection, media load, and timestamp seek where relevant. Report what actually
ran, not only what commands exist.

For retrieval results, record the corpus, licenses, model/backend, collection
dimensions, query-set revision, dev/test split, excluded negatives, hit rule,
latency hardware/network context, and artifact paths. Keep hashing-fixture checks
separate from BGE/model benchmarks. Do not replace the historical README numbers
with an unreviewed run or an invented estimate.

Preserve source attribution for all video material. Use only content you may
process and redistribute. Do not commit private media, API keys, model weights,
database files, or sensitive traces.

## Scope and safety

Keep pull requests focused and document required configuration changes. Do not
make ports public, enable deployment workflows, or invoke paid APIs without
explicit review. Actions is currently disabled. See [SECURITY.md](SECURITY.md)
for private reporting and [docs/security.md](docs/security.md) for known gaps.

The repository does not yet specify a source-code license; clarify contribution
and reuse terms with the maintainer before a substantial submission.
