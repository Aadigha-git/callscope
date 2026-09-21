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

demo: ## Start full local demo stack (Compose data plane + native processes; T-M1-11)
	@echo "T-M1-11 will implement make demo (Procfile/honcho + livekit-server --dev)."
	@echo "For now: make dev-up, then start native processes per docs/DEV_GUIDE.md."
	@$(MAKE) dev-up

demo-stop: ## Stop demo stack
	@$(MAKE) dev-down

budget: ## Show LLM spend vs CALLSCOPE_LLM_BUDGET_USD (T-M1-12)
	$(PY) -m callscope.devtools.budget_cli $(ARGS)

asr: ## Run native ASR server (fake backend by default; port 8200)
	CALLSCOPE_ASR_BACKEND=$${CALLSCOPE_ASR_BACKEND:-fake} $(PY) -m servers.asr

tts: ## Run native TTS server (fake backend by default; port 8300)
	CALLSCOPE_TTS_BACKEND=$${CALLSCOPE_TTS_BACKEND:-fake} $(PY) -m servers.tts

api: ## Run CallScope API (port 8000)
	$(PY) -m apps.api

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

test-integration: ## Also run tests needing services (set CALLSCOPE_TEST_DATABASE_URL)
	uv run pytest -m "integration or not integration"

ci: lint typecheck test backlog-validate ## Everything CI runs locally
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
