.PHONY: help install test lint clean

help:
	@echo "Available commands:"
	@echo "  install  - Install dependencies (with dev tools)"
	@echo "  test     - Run tests"
	@echo "  lint     - Run type check and linter"
	@echo "  clean    - Remove build artifacts and cache"

install:
	pip install -e ".[dev]"

test:
	PYTHONPATH=src python -m pytest

lint:
	mypy src/
	ruff check src/

clean:
	rm -rf build dist *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
