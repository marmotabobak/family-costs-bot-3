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
	@echo "    make install       - install production dependencies"
	@echo "    make install-dev   - install production + dev dependencies"
	@echo "    make db            - start postgres only (for local dev)"
	@echo "    make bot           - run bot locally"
	@echo ""
	@echo "  Docker:"
	@echo "    make up            - start all services (postgres + bot)"
	@echo "    make down          - stop all containers"
	@echo "    make logs          - follow all container logs"
	@echo "    make logs-bot      - follow bot logs"
	@echo "    make logs-db       - follow postgres logs"
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
	@echo "    make test          - run pytest"
	@echo "    make test-cov      - run tests with coverage"
	@echo ""
	@echo "  Helpers:"
	@echo "    make clean         - cleanup caches"
	@echo ""
