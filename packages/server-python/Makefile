.PHONY: dev install migrate init-dev-db init-test-db seed-dev lint test

install:
	pip install -e ".[dev,ai]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

celery-worker:
	celery -A app.celery_app worker --loglevel=info

migrate:
	alembic upgrade head

init-dev-db:
	ALLOW_DEFAULT_SEED=true python -m app.shared.infrastructure.dev_setup

init-test-db:
	python -m app.shared.infrastructure.test_db_setup

seed-dev:
	ALLOW_DEFAULT_SEED=true python -m app.shared.infrastructure.seed

migrate-create:
	alembic revision --autogenerate -m "$(msg)"

migrate-downgrade:
	alembic downgrade -1

migrate-history:
	alembic history --verbose

migrate-current:
	alembic current

lint:
	ruff check app/ tests/
	mypy app/

test:
	pytest -v

setup-db:
	psql -U postgres -c "CREATE DATABASE metaedu;" || true
	psql -U metaedu -d metaedu -c "CREATE EXTENSION IF NOT EXISTS vector;" || true
	psql -U metaedu -d metaedu -c "CREATE EXTENSION IF NOT EXISTS ltree;" || true
