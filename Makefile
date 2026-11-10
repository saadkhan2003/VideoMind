.PHONY: up down test e2e lint api web ingest-sample helm-lint tf-validate

PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest
RUFF ?= .venv/bin/ruff

up:
	docker compose -f deploy/docker-compose.yml up -d --build

down:
	docker compose -f deploy/docker-compose.yml down

test:
	$(PYTEST) -q

e2e:
	$(PYTEST) -q -m e2e

lint:
	$(RUFF) check services eval scripts

api:
	PYTHONPATH=services:services/api $(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 43124

web:
	cd services/web && API_INTERNAL_URL=http://127.0.0.1:43124 npm run dev -- --hostname 127.0.0.1 --port 43123

ingest-sample:
	PYTHONPATH=services $(PYTHON) scripts/ingest_sample.py

helm-lint:
	helm lint deploy/helm/videomind

tf-validate:
	cd deploy/terraform && terraform init -backend=false && terraform validate
