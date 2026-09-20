# -----------------------------------------------------------
# Configuration
# -----------------------------------------------------------

PYTHON := python
PIP := pip

# Paths
SRC := bot
TESTS := tests

# -----------------------------------------------------------
# Development environment
# -----------------------------------------------------------

## Create or validate .env interactively (no DB required)
.PHONY: env
env:
	$(PYTHON) scripts/config.py env

## Check whether admin user exists in DB and create if not
.PHONY: admin
admin:
	$(PYTHON) scripts/config.py admin

## Install only PROD dependencies
.PHONY: install
install:
	$(PIP) install -r requirements.txt

## Install PROD + DEV dependencies
.PHONY: install-dev
install-dev:
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

## Start only database in Docker container - for DEV only
.PHONY: db
db:
	docker compose up -d postgres

## Start bot locally w/o Docker container - for DEV only
.PHONY: bot
bot:
	$(PYTHON) -m bot.main

## Start web app locally w/o Docker container - for DEV only
.PHONY: web
web:
	uvicorn bot.web.app:app --reload --port 8000

## Start all services in Docker (database + bot)
.PHONY: up
up:
	docker compose up -d --build

## Stop all containers
.PHONY: down
down:
	docker compose down

## Follow container logs
.PHONY: logs
logs:
	docker compose logs -f

## Follow bot container logs
.PHONY: logs-bot
logs-bot:
	docker compose logs -f bot

## Follow postgres container logs
.PHONY: logs-db
logs-db:
	docker compose logs -f postgres

## Follow web container logs
.PHONY: logs-web
logs-web:
	docker compose logs -f web

# -----------------------------------------------------------
# Migrations (Alembic)
# -----------------------------------------------------------

## Apply migrations
.PHONY: migrate
migrate:
	alembic upgrade head

# -----------------------------------------------------------
# Code quality
# -----------------------------------------------------------

## Run linters
.PHONY: lint
lint:
	ruff check . --fix
	mypy .

## Install pre-commit hooks
.PHONY: hooks
hooks:
	pre-commit install

## Run pre-commit hooks
.PHONY: pre-commit
pre-commit:
	pre-commit run --all-files

# -----------------------------------------------------------
# Testing
# -----------------------------------------------------------

## Run tests
.PHONY: test
test:
	pytest -vv

## Run tests with coverage
.PHONY: test-cov
test-cov:
	pytest --cov=$(SRC) \
	       --cov-report=term \
	       --cov-report=html \
	       --cov-report=xml

## Run only serial tests (shared state / real DB — must not run in parallel)
.PHONY: test-serial
test-serial:
	pytest -vv -m serial

## Run only parallel-safe tests using all available CPU cores
.PHONY: test-parallel
test-parallel:
	pytest -vv -m "not serial" -n auto

## Run parallel-safe tests first (in parallel), then serial tests sequentially
.PHONY: test-hybrid
test-hybrid:
	pytest -vv -m "not serial" -n auto
	pytest -vv -m serial

# -----------------------------------------------------------
# Helpers
# -----------------------------------------------------------

## Delete __pycache__, pytest caches etc.
.PHONY: clean
clean:
	find . -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -f .coverage

## Show all commands
.PHONY: help
help:
	@echo ""
	@echo "Available commands:"
	@echo ""
	@echo "  Development:"
	@echo "    make env           - create or validate .env interactively (no DB required)"
	@echo "    make admin         - check/create admin user in the database"
	@echo "    make install       - install production dependencies"
	@echo "    make install-dev   - install production + dev dependencies"
	@echo "    make db            - start postgres only (for local dev)"
	@echo "    make bot           - run bot locally"
	@echo "    make web           - run web app locally"
	@echo ""
	@echo "  Docker:"
	@echo "    make up            - start all services (postgres + bot + web)"
	@echo "    make down          - stop all containers"
	@echo "    make logs          - follow all container logs"
	@echo "    make logs-bot      - follow bot logs"
	@echo "    make logs-db       - follow postgres logs"
	@echo "    make logs-web      - follow web logs"
	@echo ""
	@echo "  Database:"
	@echo "    make migrate       - apply migrations"
	@echo ""
	@echo "  Quality:"
	@echo "    make lint          - run ruff + mypy"
	@echo "    make hooks         - install pre-commit hooks"
	@echo "    make pre-commit    - run pre-commit hooks"
	@echo ""
	@echo "  Testing:"
	@echo "    make test          - run all tests sequentially"
	@echo "    make test-serial   - run only serial tests (shared state / real DB)"
	@echo "    make test-parallel - run only parallel-safe tests (uses all CPU cores)"
	@echo "    make test-hybrid   - parallel-safe tests first, then serial tests"
	@echo "    make test-cov      - run tests with coverage"
	@echo ""
	@echo "  Helpers:"
	@echo "    make clean         - cleanup caches"
	@echo ""
