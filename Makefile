.PHONY: install dev test lint format check sample docker

install:
	python -m pip install -e ".[dev]"

dev:
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
		python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	python -m pytest

lint:
	python -m ruff check .
	python -m ruff format --check .

format:
	python -m ruff format .
	python -m ruff check --fix .

check: lint test

sample:
	python scripts/generate_sample_data.py

docker:
	docker compose up --build
