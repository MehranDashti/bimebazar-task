.DEFAULT_GOAL := help
PY := python3

.PHONY: help install dev test lint format typecheck check migrate seed run hooks

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	$(PY) -m pip install -r requirements.txt

dev: ## Install dev + test dependencies
	$(PY) -m pip install -r requirements-dev.txt

test: ## Run the test suite
	$(PY) -m pytest

lint: ## Lint with ruff
	$(PY) -m ruff check .

format: ## Auto-format and fix with ruff
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

typecheck: ## Static type-check with mypy
	$(PY) -m mypy app

check: lint typecheck test ## Run lint + typecheck + tests (CI parity)

migrate: ## Apply Alembic migrations
	alembic upgrade head

seed: ## Run all seeders
	$(PY) seed.py

run: ## Start the dev server
	$(PY) run.py

hooks: ## Install pre-commit git hooks
	$(PY) -m pre_commit install
