# Contributing

Thank you for considering a contribution. This project is in active development (v0.1).

## Setup

```bash
git clone https://github.com/AnnasMazhar/agent-eval-harness
cd agent-eval-harness
uv venv && uv pip install -e '.[dev]'
```

Requires Python 3.11+. No external API keys needed — all tests run offline.

## Running the test suite

```bash
make test          # pytest -q
make lint          # ruff check . && ruff format --check .
make demo          # bash examples/run_demo.sh
```

## Making a change

1. Branch off `main`: `git checkout -b feat/<short-description>`.
2. Write tests first. Every new test must include a docstring that names the fault it
   detects. If you cannot name the fault, the test is not useful.
3. Run `make test` and `make lint` before committing.
4. Open a pull request against `main`. Include what the change does and how it was tested.

## Adding a new assertion check

1. Add a `@dataclass` class in `src/agenteval/assertions.py` that inherits from `Check`.
2. Set `id`, `description`, `severity` class attributes. `id` must be unique across all checks.
3. Implement `evaluate(self, run: Run) -> CheckResult`.
4. Register it in `_CHECK_REGISTRY` at the bottom of `assertions.py` so it can be loaded from YAML.
5. Add tests to `tests/test_assertions.py`:
   - One test where a good run passes the check.
   - One test where a bad run fails the check.
   - Each test docstring must name the fault caught.

## Adding a new statistical routine

1. Implement in `src/agenteval/scoring.py`.
2. Add a known-answer test (KAT) in `tests/test_scoring.py` with a hand-computed expected
   value shown in a comment. The expected value must come from outside the codebase (paper,
   textbook, or a manual calculation written out step-by-step).
3. Update `docs/IMPLEMENTATION-NOTES.md` with the equation → code mapping.

## Code standards

- Type annotations on every public function.
- Docstrings on every public class and function.
- No bare `except:`. No swallowed exceptions.
- `ruff check .` and `ruff format --check .` must pass before every commit.
- No network calls in tests. Fixtures and synthetic data only.
- No emojis in code or docs.

## Commit style

Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`.
No AI attribution in commits (no `Co-Authored-By` trailers).
Keep the subject line under 72 characters.

## Bug reports

Open an issue with:
- Python version and OS.
- The exact command that failed.
- The full traceback.
- A minimal reproducer (a JSONL recording or a contract YAML if relevant).

## Good first issues

Look for the `good first issue` label. The most common ones:
- Adding a new PII pattern to `PII_PATTERNS` in `assertions.py`.
- Adding a test for an edge case documented in `docs/ADVERSARIAL_REVIEW.md`.
- Improving an error message to include the offending value.

## What not to contribute (for now)

- New CLI commands not listed in the spec.
- Dependencies beyond `pyyaml` and `jsonschema` (stdlib only otherwise).
- LLM-as-judge scoring — it is in the roadmap but out of scope for v0.1.
