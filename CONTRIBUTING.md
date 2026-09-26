# Contributing

## Setup

```bash
uv venv && uv pip install -e '.[dev]'
```

## Running tests

```bash
make test
```

## Linting

```bash
make lint
```

## Adding a new assertion check

1. Add a `@dataclass` class in `src/agenteval/assertions.py` inheriting from `Check`.
2. Set `id`, `description`, `severity` class attributes.
3. Implement `evaluate(self, run: Run) -> CheckResult`.
4. Register it in `_CHECK_REGISTRY` at the bottom of `assertions.py`.
5. Add KAT tests to `tests/test_assertions.py` with a docstring naming the fault
   the test detects.

## Commit style

Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`.
No AI attribution in commits.

## Quality bar

- Every public function has type annotations and a docstring.
- Every new statistical routine needs a KAT with a hand-computed expected value.
- `ruff check .` and `ruff format --check .` must pass.
- New tests must name the fault they detect in their docstring.
