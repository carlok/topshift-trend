PYTHON ?= python3

.PHONY: test lint up logs

test:
	$(PYTHON) -m pytest --cov=bot --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m mypy bot

up:
	podman compose up -d

logs:
	podman compose logs -f

