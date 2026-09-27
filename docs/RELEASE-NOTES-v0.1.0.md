# Release Notes — replayproof v0.1.0

**Tag:** v0.1.0
**Branch:** proof/release-v0.1
**Date:** 2026-09-27

---

## Install

```bash
pip install replayproof-0.1.0-py3-none-any.whl
# or from source:
pip install git+https://github.com/AnnasMazhar/replayproof
```

**SHA256 of wheel:**

```
cc81e37628a3ff385536bd1cc9736e0f29bff76b957198582b28daa2f58e5a94  replayproof-0.1.0-py3-none-any.whl
```

Verify before installing:

```bash
sha256sum replayproof-0.1.0-py3-none-any.whl
```

---

## What this release includes

**Offline, keyless agent-run evaluation.** Reads recorded agent runs in JSONL format
(its own schema or OpenAI/Anthropic-style message lists) and evaluates them against
a YAML contract without any live LLM or network call.

**Contract checking.** Declare what a correct agent run looks like in `contracts/*.yaml`:
required tools, forbidden tools, max tool calls, max tokens, no-pattern (PII, secrets),
final answer non-empty, argument JSON schema, max latency. Each check has a stable `id`
and `severity` (error/warn).

**Regression gate.** `agenteval gate` compares a current result JSON against a committed
baseline. Exits 1 if pass_rate drops, total tokens increase >10%, p95 latency increases
>25%, or total cost increases >10%.

**Pass-rate statistics.** All pass rates are reported with a 95% Wilson score lower bound
(Wilson 1927, JASA 22(158):209-212; verified against D'Oro et al. 2026 arXiv 2605.08261).
For n=4/4 the lower bound is 51.0% — reflecting that a sample of 4 is too small to claim
high reliability.

**Drift detection.** `agenteval drift` classifies per-case changes between two result
JSONs as: regression, fix, churn (same fail, different reason), stable pass, stable fail.

**Real recorded runs on this machine.** `recordings/real_run.jsonl` contains 6 genuine
agent runs produced by `examples/research_agent.py` (a deterministic Python function,
no LLM) against the research contract. These are not fixtures — they are real runs from
this machine with real latency measurements.

---

## Post-download smoke test

From a fresh temp directory (no repo checkout needed):

```bash
# Install the wheel
pip install replayproof-0.1.0-py3-none-any.whl

# Clone the recordings and contracts (or use your own)
git clone https://github.com/AnnasMazhar/replayproof /tmp/rp-src

# Run against the real recording
agenteval run \
    --contract /tmp/rp-src/contracts/research.yaml \
    --runs /tmp/rp-src/recordings/real_run.jsonl \
    --output /tmp/smoke_result.json

agenteval gate \
    --baseline /tmp/rp-src/recordings/real_run_baseline.json \
    --current /tmp/smoke_result.json

agenteval drift \
    --a /tmp/rp-src/recordings/real_run_baseline.json \
    --b /tmp/smoke_result.json
```

**Expected output (run 2026-09-27T15:47 UTC from wheel):**

```
# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 6 |
| Passed | 6 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 61.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd

Regressions : 0
Fixes       : 0
Churn       : 0
Stable pass : 6
Stable fail : 0
Token delta : +0
```

---

## What works

- `agenteval run`, `gate`, `drift`, `record` commands — all functional, all offline.
- 138 tests passing on Python 3.11–3.13. Ruff clean.
- Wheel installs from source without any API keys.
- Deterministic replay: 100 dry replays of the real recording produce identical output.
- Wilson lower bound verified against independent derivation (statistics.NormalDist) and
  hand computation (matches D'Oro et al. 2026 §4.2 exactly).
- Mutation score 82.6% on `scoring.py` (>70% target; EVIDENCE.md §7).
- Paper traceability: 6 cited papers traced to implementation + experiment
  (`docs/PAPER-TRACEABILITY.md`; CI check `scripts/check_research_traceability.py`).

## What does not work in this release

- **No LLM recording support.** The `agenteval record` command runs a deterministic
  Python agent. Recording a live LLM requires injecting the token counts and latency
  yourself; there is no provider integration.
- **No Inspect `.eval` log reader.** `scripts/convert_inspect_log.py` converts the
  Inspect log.json format; the native `.eval` zip reader is not yet a first-class CLI
  subcommand.
- **No judge-based scoring.** The `final_answer_matches` check uses regex; semantic
  correctness requires a separate judge layer (listed in Roadmap).
- **Gate integrity.** `agenteval gate` reads a JSON file; it cannot verify the file was
  produced by an actual test run. A developer can hand-craft the JSON. This is an accepted
  design limitation for v0.1 — CI integrity is the caller's responsibility.
- **PII detection is regex-based.** Unicode homoglyphs (fullwidth @, Cyrillic letters)
  bypass the email regex. Only structured PII (standard ASCII email, SSN, phone, credit
  card) is detected.
- **Wilson lower bound for n < 5 may be too conservative.** For 5/5, the 95% lower bound
  is 56.6% — useful as a relative measure but too conservative for absolute thresholds.
  Use drop-based gates for small suites.

---

## Open adversarial findings at release time

All blockers: 0. All majors fixed. Minor/limitation items accepted:

| id | severity | finding | status |
|---|---|---|---|
| AR-MIN-1 | minor | Gate integrity: hand-crafted JSON passes | accepted limitation (README L261-263) |
| AR2-MIN-1 | minor | PII regex bypassed by Unicode homoglyphs | accepted limitation (README Limitations) |
| AR2-MIN-3 | minor | Forbidden/required tool checks are case-sensitive | accepted limitation |
| C2P11-MAJ-1 | major | wilson_lower accepted negative confidence | **FIXED** (ValueError raised) |
| C2P11-MAJ-2 | major | Gate accepted NaN/inf pass_rate | **FIXED** (ValueError raised) |
| ADV2-1 | major | contracts/research.yaml missing from root | **FIXED** (contracts/ dir created) |
| ADV2-2 | major | scripts/convert_inspect_log.py missing | **FIXED** (scripts/ dir created) |
| AR-MAJ-3 | major | test_markdown_no_timestamps regex too narrow | **FIXED** (broadened pattern) |

---

## How to reproduce results

All claims are reproducible from source:

```bash
git clone https://github.com/AnnasMazhar/replayproof
cd replayproof
uv venv && uv pip install -e '.[dev]'
pytest -q                         # 138 tests
bash examples/run_demo.sh         # end-to-end demo
python scripts/check_research_traceability.py  # paper CI check
```
