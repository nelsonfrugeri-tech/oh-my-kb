.DEFAULT_GOAL := help
SHELL := /bin/bash

UV ?= uv
PKG := oh_my_kb

.PHONY: help venv install sync test lint format typecheck check clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make \033[36m<target>\033[0m\n\nTargets:\n"} \
		/^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

venv: ## Create the virtualenv and install all dependencies (alias: install)
	$(UV) sync

install: venv ## Alias for `venv`

sync: venv ## Alias for `venv`

test: ## Run the test suite
	$(UV) run pytest

lint: ## Lint the codebase with ruff
	$(UV) run ruff check .

format: ## Format the codebase with ruff
	$(UV) run ruff format .

typecheck: ## Type-check the package with mypy
	$(UV) run mypy $(PKG)

check: lint typecheck test ## Run lint, type-check and tests (CI gate)

clean: ## Remove the virtualenv and tool caches
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
