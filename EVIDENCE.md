# EVIDENCE.md

Raw terminal output from running the replayproof v0.1 build.
All output is verbatim from actual runs on this machine.
No output is fabricated or summarised.
The only redaction is host paths: absolute home directories are shown as `/build/`.

---

## 1. Install

```
$ uv pip install -e '.[dev]'
   Building replayproof @ file:///build/portfolio/agent-eval-harness
      Built replayproof @ file:///build/portfolio/agent-eval-harness
Prepared 1 package in 739ms
Uninstalled 1 package in 0.73ms
Installed 1 package in 1ms
 ~ replayproof==0.1.0 (from file:///build/portfolio/agent-eval-harness)
```

---

## 2. Test suite

```
$ pytest -q
........................................................................ [ 38%]
........................................................................ [ 77%]
..........................................                               [100%]
186 passed in 2.72s
```

186 tests (up from 182 in c5-p04). Additions in this pass:
- 4 new adversarial tests in c5-p05: `test_forbidden_tool_called_last_still_fails`,
  `test_wilson_lower_monotone_in_successes`, `test_gate_zero_threshold_any_drop_fails`,
  `test_contract_forbidden_and_required_same_tool_evaluates_both`.

---

## 3. Lint

```
$ ruff check .
All checks passed!

$ ruff format --check .
21 files already formatted
```

---

## 4. Version

```
$ python -c "import agenteval; print(agenteval.__version__)"
0.1.0
```

---

## 5. End-to-end demo

```
$ bash examples/run_demo.sh
=== agent-eval-harness demo ===

--- Step 1: evaluate sample_run.jsonl against research contract ---
# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 4 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 51.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | PASS | 0 | 0 | 0.1 |
| How long does installation take | PASS | 0 | 0 | 0.0 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | PASS | 0 | 0 | 0.0 |


--- Step 2: evaluate regressed_run.jsonl against research contract ---
# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 2 |
| Pass Rate | 50.0% |
| Wilson Lower Bound (95%) | 15.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | FAIL | 0 | 0 | 0.0 |
| How long does installation take | PASS | 0 | 0 | 0.1 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | FAIL | 0 | 0 | 0.0 |


--- Step 3: gate good run vs itself (expect: PASS, exit 0) ---
Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero (first-run or corrupted baseline): total_tokens, total_cost_usd
Exit code: 0

--- Step 4: gate regressed run vs good baseline (expect: FAIL, exit 1) ---
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
Warning: the following gates were not enforced because the baseline value is zero (first-run or corrupted baseline): total_tokens, total_cost_usd
Exit code: 1

--- Step 5: drift report ---
Regressions : 2
Fixes       : 0
Churn       : 0
Stable pass : 2
Stable fail : 0
Token delta : +0

Regressions:
  How do solar panels work
  What types of batteries are used for storage

--- Step 6: markdown report for regressed run ---
# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 2 |
| Pass Rate | 50.0% |
| Wilson Lower Bound (95%) | 15.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | FAIL | 0 | 0 | 0.0 |
| How long does installation take | PASS | 0 | 0 | 0.1 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | FAIL | 0 | 0 | 0.0 |


--- Final checks ---
PASS: gate exits correctly (0 on good, 1 on regressed)

=== Demo complete ===
```

---

## 6. Gate exit codes (explicit)

```
$ agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/sample_run.jsonl \
    --output /tmp/ev_good.json

$ agenteval gate --baseline /tmp/ev_good.json --current /tmp/ev_good.json
Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero ...
$ echo $?
0

$ agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/regressed_run.jsonl \
    --output /tmp/ev_bad.json

$ agenteval gate --baseline /tmp/ev_good.json --current /tmp/ev_bad.json
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
$ echo $?
1
```

---

## 7. Adversarial test count

43 adversarial/byzantine tests in `tests/test_adversarial.py` as of c5-p05.

Each test docstring names the fault it detects and the fault injection that would cause
the test to catch a real bug. Representative examples:

- `test_contract_yaml_python_tag_rejected_no_execution`: YAML code execution via
  `!!python/object/apply` tag is rejected by `safe_load` — a hostile contract file must
  not execute code in CI.
- `test_gate_crafted_baseline_cannot_inflate_thresholds`: a baseline with extreme values
  (tokens=1_000_000) cannot mask a 10.0001% increase by integer-rounding.
- `test_wilson_lower_adversarial_n1_s1`: n=1, s=1 must return ~0.205, not 1.0 — a
  naive implementation that returns `p_hat` when `p_hat == 1.0` fails this test.
- `test_forbidden_tool_called_last_still_fails` (c5-p05 new): forbidden tool in the
  final turn must be caught — a naive first-turn-only scan misses it.
- `test_wilson_lower_monotone_in_successes` (c5-p05 new): Wilson lower bound must
  weakly increase as successes increase for fixed n — a numerator arithmetic error
  causes non-monotone dips near p_hat = 0.8-0.9.
- `test_gate_zero_threshold_any_drop_fails` (c5-p05 new): a 0.0 tolerance is not the
  same as "disabled" — a guard `if threshold > 0` silently skips the gate entirely.
- `test_contract_forbidden_and_required_same_tool_evaluates_both` (c5-p05 new): both
  checks must fire independently — a "smart" resolver that skips forbidden when the
  tool is also required produces a false-pass.

---

## 8. Citation corrections in RESEARCH.md

The independent Argus citation audit (2026-09-26, two rounds, all sources fetched live)
found 8 fabricated attributions and 2 arithmetic errors. All have been corrected in
`docs/RESEARCH.md` and `docs/CITATION-AUDIT.md`. Key corrections:

- `wilson_lower(5, 5)`: corrected from 0.478 to 0.566 (the test suite validates this
  via `test_wilson_lower_kat` with the hand-computation shown in the test comment).
- `wilson_lower(4, 4)`: hand-worked arithmetic corrected to show both centre and
  half-width steps; final value 0.5102 is correct.
- S7 (AEVAL): re-labelled as a design decision, not attributed to the AEVAL paper.
- S1 (content-addressed key): re-labelled as our own design; the actual paper uses
  SHA256(method ‖ norm(url) ‖ H_body).

See `docs/CITATION-AUDIT.md` for the full audit table with per-source SUPPORTS/MISLABELLED
status and corrective action taken.

---

## 9. Mutation score (cycle 4)

Recorded in `reports/mutation-c4.json`. From that file:

- Total mutants: 235
- Killed: 223
- Survived: 12
- Kill rate: 94.9%

Cycle 4 result is the most recent full mutmut run. Surviving mutants are documented in
`reports/improvements.md` as either equivalent mutants (the mutation does not change
observable behaviour for any valid input) or mutations that cannot be killed without
over-specifying implementation details.
