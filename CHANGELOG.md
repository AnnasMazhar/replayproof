# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] - 2026-09-26

### Added
- `src/agenteval/transcript.py`: frozen dataclasses (`ToolCall`, `Turn`, `Run`) with
  JSONL serialisation and forward-compatible loading.
- `src/agenteval/record.py`: `Recorder` wrapping any callable agent with deterministic
  clock injection; `from_messages()` for OpenAI/Anthropic-style message lists.
- `src/agenteval/replay.py`: `replay()` with `strict`, `lenient`, and `dry` modes;
  `ReplayMismatch` with `expected` and `actual` fields.
- `src/agenteval/assertions.py`: 10 assertion check types (`tool_sequence`,
  `required_tools`, `forbidden_tools`, `arg_schema`, `max_tool_calls`, `max_tokens`,
  `max_latency_ms`, `no_pattern`, `final_answer_matches`, `final_answer_not_empty`);
  `Contract` loadable from YAML; `PII_PATTERNS` dict.
- `src/agenteval/scoring.py`: `wilson_lower()` (Wilson 1927 score interval, no scipy);
  `pass_rate()`, `CaseResult`, `SuiteResult`, `compute_suite()`, `Pricing`.
- `src/agenteval/budget.py`: `Baseline`, `compare()`, `GateReport` with per-metric
  trip details.
- `src/agenteval/drift.py`: `drift()` with verdict classification (regression / fix /
  churn / stable_pass / stable_fail).
- `src/agenteval/report.py`: `to_markdown()` (stable, no timestamps) and `to_html()`
  (self-contained, no CDN, no JS).
- `src/agenteval/cli.py`: `agenteval` CLI with commands `record`, `replay`, `run`,
  `gate`, `drift`, `report`.
- `examples/`: deterministic sample agent, YAML contract, committed recordings, demo
  script.
- `tests/`: 94 tests across KAT, property-based (Hypothesis), and integration layers.
- `docs/`: `RESEARCH.md` (13 verified links), `IMPLEMENTATION-NOTES.md` (full
  traceability), `DESIGN.md`, `ADVERSARIAL_REVIEW.md`.
- `EVIDENCE.md`: verbatim terminal output for all 7 required evidence sections.
- Mutation score: 82.6% (181/219 killed on `scoring.py`).
