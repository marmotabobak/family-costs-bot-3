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

## Install only PROD dependencies
install:
	$(PIP) install -r requirements.txt

## Install PROD + DEV dependencies
install-dev:
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

## Start only database in Docker container - for DEV only:
db:
	docker-compose up -d postgres

## Start bot locally w/o Docker container - for DEV only:
bot:
	$(PYTHON) -m bot.main


## Start all services in Docker (database + bot)
up:
	docker-compose up -d --build

## Stop all containers
down:
	docker-compose down

## Follow container logs
logs:
	docker-compose logs -f

## Follow bot container logs
logs-bot:
	docker-compose logs -f bot

## Follow postgres container logs
logs-db:
	docker-compose logs -f postgres

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
db-rev:
	alembic current

## Show available Alembic heads
db-heads:
	alembic heads

# -----------------------------------------------------------
# Code quality
# -----------------------------------------------------------

## Run linters
lint:
	ruff check . --fix
	mypy .

## Install pre-commit hooks
hooks:
	pre-commit install

## Run pre-commit jooks
pre-commit:
	pre-commit run --all-files

# -----------------------------------------------------------
# Testing
# -----------------------------------------------------------

## Run tests
test:
	pytest -vv

## Run tests with coverage
test-cov:
	pytest --cov=$(SRC) \
	       --cov-report=term \
	       --cov-report=html \
	       --cov-report=xml


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
	@echo ""
	@echo "  Development:"
	@echo "    make deps        - install production deps"
	@echo "    make deps-dev    - install dev deps"
	@echo "    make db          - start postgres only (for local dev)"
	@echo "    make bot         - run bot locally"
	@echo ""
	@echo "  Docker:"
	@echo "    make up          - start all services (postgres + bot)"
	@echo "    make down        - stop all containers"
	@echo "    make logs        - follow all container logs"
	@echo "    make logs-bot    - follow bot logs"
	@echo "    make logs-db     - follow postgres logs"
	@echo ""
	@echo "  Database:"
	@echo "    make migrate     - apply migrations"
	@echo "    make migration m=\"msg\" - create migration"
	@echo "    make downgrade   - rollback 1 migration"
	@echo "    make db-rev      - show current revision"
	@echo "    make db-heads    - show available heads"
	@echo ""
	@echo "  Quality:"
	@echo "    make lint        - run ruff + mypy"
	@echo "    make hooks       - install pre-commit hooks"
	@echo "    make pre-commit  - run pre-commit hooks"
	@echo "    make test        - run pytest"
	@echo "    make test-cov         - run tests with coverage"
	@echo ""
	@echo "    make clean       - cleanup caches"
	@echo ""
