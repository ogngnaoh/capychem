# Shortcuts for the legacy benchmark app. Studio setup is in README.md.
.DEFAULT_GOAL := help
.PHONY: help setup dev api web db test check

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Install legacy benchmark dependencies and start PostgreSQL
	uv sync --frozen --python 3.12
	uv sync --frozen --project harness
	pnpm install --frozen-lockfile
	cp -n .env.example .env.local || true
	docker compose -f infra/compose.yml up -d postgres
	@echo "Setup complete. Run 'make dev' to start the API + web."

db: ## Start local Postgres (localhost:5432; no cloud, no SQLite fallback)
	docker compose -f infra/compose.yml up -d postgres

api: ## FastAPI backend on :8000
	uv run uvicorn capychem.api.main:app --reload

web: ## Next.js frontend on :3000
	pnpm --filter web dev

dev: ## API + web together (Ctrl-C stops both)
	@echo "Starting API (:8000) and web (:3000)..."
	uv run uvicorn capychem.api.main:app --reload & \
	pnpm --filter web dev; \
	kill %1 2>/dev/null || true

test: ## Backend + web test suites (needs Postgres + harness venv)
	uv run pytest
	pnpm --filter web test

check: ## Python lint and types, legacy web types and lint
	uv run mypy -p capychem -p capychem.api
	uv run ruff check .
	pnpm --filter web typecheck
	pnpm --filter web lint
