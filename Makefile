.PHONY: install test lint format demo

install:
	uv pip install -e '.[dev]'

test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format:
	.venv/bin/ruff format .

demo:
	bash examples/run_demo.sh
