.PHONY: install dev test lint format check sample docker

install:
	python -m pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

check: lint test

sample:
	python scripts/generate_sample_data.py

docker:
	docker compose up --build
