.PHONY: dev install install-dev lint test

install:
	uv sync --frozen --no-dev

install-dev:
	uv sync --frozen

dev:
	uv run --frozen python -m mcp_server.main

lint:
	uv run --frozen ruff check .

test:
	uv run --frozen pytest -q
