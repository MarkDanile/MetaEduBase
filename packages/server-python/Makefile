.PHONY: dev install migrate lint test

install:
	pip install -e ".[dev,ai]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

celery-worker:
	celery -A app.celery_app worker --loglevel=info

migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(msg)"

lint:
	ruff check app/ tests/
	mypy app/

test:
	pytest -v

setup-db:
	psql -U postgres -c "CREATE DATABASE metaedu;" || true
	psql -U metaedu -d metaedu -c "CREATE EXTENSION IF NOT EXISTS vector;" || true
	psql -U metaedu -d metaedu -c "CREATE EXTENSION IF NOT EXISTS ltree;" || true
