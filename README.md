# agent-eval-harness

[![CI](https://github.com/openclaw/agent-eval-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/openclaw/agent-eval-harness/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Deterministic, offline-replayable regression testing for LLM agents.

## What problem this solves

Agent behaviour is software behaviour: it should be recorded, replayed, asserted, and
compared across model versions without requiring live API calls. Most LLM evaluation
frameworks require network access on every CI run, produce non-deterministic results, and
give no way to tell whether a model update regressed behaviour or just changed it. This
harness records agent runs to JSONL, replays them offline against contracts, computes
honest confidence intervals on pass rates, and gates CI on regressions.

## Design

```
Record agent run  ──►  Run.jsonl  ──►  Contract.evaluate  ──►  CaseResult[]
                                              │
                               ┌──────────────┴──────────────┐
                               ▼                             ▼
                          SuiteResult                   SuiteResult
                         (current)                      (baseline)
                               │                             │
                               └──────────┬──────────────────┘
                                          ▼
                                     GateReport          DriftReport
                                   (CI pass/fail)     (model A vs B diff)
                                          │
                                          ▼
                                    Markdown / HTML report
```

## Install

```bash
uv venv && uv pip install -e '.[dev]'
```

No API keys required. All tests run offline.

## 60-second quickstart

```bash
# Run the end-to-end demo (uses committed fixture recordings — no LLM needed)
bash examples/run_demo.sh
```

Or step by step:

```bash
# Evaluate the good sample run against the research contract
agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/sample_run.jsonl \
    --output /tmp/sample_result.json

# Gate: verify regressed run fails
agenteval gate \
    --baseline /tmp/sample_result.json \
    --current examples/recordings/regressed_result.json
# Exit code 1 — regression detected
```

## Real results

Generated from `bash examples/run_demo.sh` on 2026-09-26:

**Good run (sample_run.jsonl):**

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 4 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 51.0% |
| p95 Latency | 0.1 ms |

**Regressed run (regressed_run.jsonl):**

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 2 |
| Pass Rate | 50.0% |
| Wilson Lower Bound (95%) | 15.0% |

**Drift:**

| Metric | Value |
| ------ | ----- |
| Regressions | 2 |
| Fixes | 0 |
| Stable pass | 2 |

Gate exit code: 1 on regressed run, 0 on good run.

## How the gates work

The gate compares four metrics between a stored baseline and the current run:

- **pass_rate**: any drop triggers (threshold 0.0 by default, configurable)
- **total_tokens**: increase > 10% triggers
- **p95_latency_ms**: increase > 25% triggers
- **total_cost_usd**: increase > 10% triggers

Pass rates are reported with a **Wilson score interval lower bound** at 95% confidence.
This is more conservative than the normal approximation near p=0 and p=1, which is
where real eval suites operate (pass rates cluster near 100% or drop sharply on regression).

For a suite with 4/4 passing, the Wilson lower bound is 51.0% — reflecting that a sample
of 4 is too small to claim high reliability, even with 100% observed pass rate. This
prevents false confidence from small suites.

Reference: Wilson (1927), *JASA* 22(158):209-212. Applied to LLM evals:
D'Oro et al. (2026), arxiv 2605.08261.

## Limitations

- **Replay cannot validate non-deterministic sampling.** Dry-mode replay freezes the LLM
  output; it does not test whether the LLM would produce the same output given live
  inputs. This is by design — the harness tests the deterministic scaffold (tool routing,
  argument handling, contract evaluation).

- **Judge-based scoring is not implemented.** There is no LLM-as-judge eval in v0.1.
  The `final_answer_matches` check uses regex; semantic correctness requires a separate
  judge layer.

- **Gate integrity relies on the caller.** `agenteval gate` reads a JSON file; it cannot
  verify the file was produced by an actual test run. In CI, the workflow must generate
  the file and pass it to the gate in the same job.

- **Wilson lower bound is conservative for small n.** For n < 10, the 95% Wilson lower
  bound may be too conservative to be useful as an absolute threshold. Use relative
  (drop-based) gates for small suites.

- **PII detection is regex-based.** The `no_pattern` check uses deterministic regexes.
  It detects structured PII (email, SSN, phone, credit card) but not free-form PII
  (names, addresses, unformatted numbers).

## Roadmap

- Hierarchical bootstrap for nested evaluation structures
- Judge-based scoring plugin API
- HTML report with per-case expandable details
- Cost estimation from provider pricing APIs
- Baseline integrity signing (HMAC or content-addressable storage)
