# Recipe lines must start with a real tab (GNU Make / BSD Make compatible).
.DEFAULT_GOAL := help
PY := uv run python

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

setup: ## Install deps and git hooks
	@test -d .git || git init -b main
	uv sync --extra dev
	uv run pre-commit install
	@test -f .env || cp .env.example .env
	@echo "Edit .env (never commit it)."

dev-up: ## Start local services (Postgres, MinIO, Prometheus, Grafana)
	docker compose -f docker-compose.local.yml up -d

dev-down: ## Stop local services
	docker compose -f docker-compose.local.yml down

demo: ## Start Compose data plane + native Procfile (API/ASR/TTS/worker/web/livekit)
	@chmod +x scripts/demo_start.sh scripts/demo_stop.sh
	@./scripts/demo_start.sh

demo-stop: ## Stop honcho natives + Compose data plane
	@chmod +x scripts/demo_start.sh scripts/demo_stop.sh
	@./scripts/demo_stop.sh

compose-validate: ## Validate local Compose + Prometheus/Grafana demo wiring
	uv run pytest tests/infra/test_compose_config.py -q --no-cov

budget: ## Show LLM spend vs CALLSCOPE_LLM_BUDGET_USD (T-M1-12)
	$(PY) -m callscope.devtools.budget_cli $(ARGS)

eval: ## Eval runner: make eval ARGS='run --stack local-mac-dev --dataset golden-eval@v1'
	$(PY) -m callscope.devtools.eval_cli $(ARGS)

governance: ## Model/stack registry: make governance ARGS='backfill|list-models|list-stacks'
	$(PY) -m callscope.devtools.governance_cli $(ARGS)

experiment: ## Experiments: make experiment ARGS='e1|hotwords ...'
	$(PY) -m callscope.devtools.experiment_cli $(ARGS)

load: ## Local concurrency/latency load (T-M6-01): make load ARGS='--reps 3'
	$(PY) -m callscope.devtools.load_cli $(ARGS)

dataset: ## Dataset CLI: make dataset ARGS='build|validate|ingest-recorded|...'
	$(PY) -m callscope.devtools.dataset_cli $(ARGS)

asr: ## Run native ASR server (fake backend by default; port 8200)
	CALLSCOPE_ASR_BACKEND=$${CALLSCOPE_ASR_BACKEND:-fake} $(PY) -m servers.asr

tts: ## Run native TTS server (fake backend by default; port 8300)
	CALLSCOPE_TTS_BACKEND=$${CALLSCOPE_TTS_BACKEND:-fake} $(PY) -m servers.tts

api: ## Run CallScope API (port 8000)
	$(PY) -m apps.api

review: ## Streamlit Call Review console (port 8501); needs `make api`
	uv run --extra review streamlit run apps/review/app.py --server.port 8501

review-seed: ## Seed 40 synthetic review calls via API
	$(PY) -m callscope.devtools.review_cli seed-demo --n 40

biz: ## Run Lakeside Business API (port 8100)
	$(PY) -m apps.biz

worker: ## Voice worker: MOCK=1 for smoke, else --serve metrics (:9100)
	@if [ "$(MOCK)" = "1" ]; then \
		$(PY) -m apps.worker --mock-call; \
	else \
		CALLSCOPE_METRICS_PORT=$${CALLSCOPE_METRICS_PORT:-9100} $(PY) -m apps.worker --serve; \
	fi

purge: ## Retention purge (DRY=1 default; APPLY=1 to delete). delete-call: make purge DELETE=<uuid>
	@if [ -n "$(DELETE)" ]; then \
		$(PY) -m callscope.devtools.retention_cli delete-call $(DELETE); \
	elif [ "$(APPLY)" = "1" ]; then \
		$(PY) -m callscope.devtools.retention_cli purge --apply; \
	else \
		$(PY) -m callscope.devtools.retention_cli purge --dry-run; \
	fi

hermes-selftest: ## Fail closed if Hermes toolset allowlist drifts (T-M1-09)
	$(PY) infra/hermes/toolset_selftest.py --config infra/hermes/config.yaml

web-install: ## npm install for apps/web
	cd apps/web && npm install

web-test: ## Vitest for apps/web
	cd apps/web && npm test

web-build: ## Production build of apps/web
	cd apps/web && npm run build

web-dev: ## Vite dev server (proxies /v1 → :8000)
	cd apps/web && npm run dev

db-upgrade: ## Apply Alembic migrations to CALLSCOPE_DATABASE_URL (or settings default)
	uv run alembic upgrade head

db-downgrade: ## Downgrade one Alembic revision
	uv run alembic downgrade -1

db-current: ## Show current Alembic revision
	uv run alembic current

lint: ## Ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Auto-format
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## mypy (strict) on callscope/ + servers/
	uv run mypy

test: ## Unit + contract tests with coverage gate
	uv run pytest

security-test: ## Design §8.3 local-demo security suite (T-M6-02)
	uv run pytest -m security --cov-fail-under=0

test-integration: ## Also run tests needing services (set CALLSCOPE_TEST_DATABASE_URL)
	uv run pytest -m "integration or not integration"

ci: lint typecheck test backlog-validate compose-validate ## Everything CI runs locally
	@echo "CI parity OK"

backlog-validate: ## Validate backlog/tasks.yaml
	$(PY) -m callscope.devtools.backlog validate

backlog-render: ## Regenerate docs/BACKLOG.md from tasks.yaml
	$(PY) -m callscope.devtools.backlog render

status: ## Usage: make status T=T-M1-03 S=in_progress
	$(PY) -m callscope.devtools.backlog status $(T) $(S) && $(PY) -m callscope.devtools.backlog render

sprint: ## Usage: make sprint N=S1 T=T-M0-01,T-M0-02
	$(PY) -m callscope.devtools.backlog sprint $(N) $(T) && $(PY) -m callscope.devtools.backlog render

report: ## Usage: make report SPRINT=S1  (or MILESTONE=M1)
	$(PY) -m callscope.devtools.backlog report $(if $(SPRINT),--sprint $(SPRINT),--milestone $(MILESTONE))

issues: ## Create GitHub issues for tasks without one (needs gh auth)
	$(PY) -m callscope.devtools.backlog issues

check-artifacts: ## Local run of the PR artifact gate
	$(PY) -m callscope.devtools.check_artifacts origin/main

build: ## Build wheel + sdist
	uv build

design-md: ## Convert the Word design doc to Markdown for Cursor (needs pandoc)
	pandoc docs/design/*.docx -t gfm --wrap=none -o docs/design/CallScope_Phase3_Design.md

clean: ## Remove caches and build output
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build htmlcov .coverage
