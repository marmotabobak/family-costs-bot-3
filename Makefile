# -----------------------------------------------------------
# Configuration
# -----------------------------------------------------------

PYTHON := python
PIP := pip

# Paths
SRC := bot
TESTS := tests

# DB
DATABASE_URL := $(DATABASE_URL)

# -----------------------------------------------------------
# Development environment
# -----------------------------------------------------------

## Install only production dependencies
deps:
	$(PIP) install -r requirements.txt

## Install production + dev dependencies
deps-dev:
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

## Start PostgreSQL locally via Docker
up:
	docker-compose up -d

## Stop containers
down:
	docker-compose down

## Check container logs
logs:
	docker-compose logs -f

# -----------------------------------------------------------
# Migrations (Alembic)
# -----------------------------------------------------------

## Create new migration (autogenerate)
migration:
	alembic revision --autogenerate -m "$(m)"

## Apply migrations
migrate:
	alembic upgrade head

## Roll back 1 migration
downgrade:
	alembic downgrade -1

## Show current Alembic revision
rev:
	alembic current

## Show available heads
heads:
	alembic heads

# -----------------------------------------------------------
# Code quality
# -----------------------------------------------------------

## Run ruff linter
lint:
	ruff check . --fix
	mypy .

## Install pre-commit hooks
hooks:
	pre-commit install

## Run pre-commit on all files
pre-commit:
	pre-commit run --all-files

# -----------------------------------------------------------
# Testing
# -----------------------------------------------------------

## Run tests
test:
	pytest -vv

## Run tests with coverage
cov:
	pytest --cov=$(SRC) \
	       --cov-report=term \
	       --cov-report=html \
	       --cov-report=xml

# -----------------------------------------------------------
# Application
# -----------------------------------------------------------

## Run application
run:
	$(PYTHON) -m bot.main

# -----------------------------------------------------------
# Helpers
# -----------------------------------------------------------

## Delete __pycache__, pytest caches etc.
clean:
	find . -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -f .coverage

## Show all commands
help:
	@echo ""
	@echo "Available commands:"
	@echo "  make deps          - install production deps"
	@echo "  make deps-dev      - install dev deps"
	@echo "  make up            - start postgres"
	@echo "  make down          - stop postgres"
	@echo "  make logs          - follow docker logs"
	@echo "  make migration m=\"message\" - create alembic migration"
	@echo "  make migrate       - apply migrations"
	@echo "  make downgrade     - rollback migration"
	@echo "  make rev           - show current DB revision"
	@echo "  make heads         - show heads"
	@echo "  make lint          - run ruff + mypy"
	@echo "  make hooks         - install pre-commit hooks"
	@echo "  make pre-commit    - run pre-commit on all files"
	@echo "  make test          - run pytest"
	@echo "  make cov           - run tests with coverage"
	@echo "  make run           - run app"
	@echo "  make clean         - cleanup caches"
	@echo ""
