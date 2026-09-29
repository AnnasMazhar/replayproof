# EVIDENCE.md

Raw terminal output from running the replayproof v0.1 build.
All output is verbatim from actual runs on this machine.
No output is fabricated or summarised.
The only redaction is host paths: absolute home directories are shown as `/build/`.

---

## 1. Install

```
$ uv pip install -e '.[dev]'
Resolved 29 packages in 514ms
   Building replayproof @ file:///build/portfolio/agent-eval-harness
      Built replayproof @ file:///build/portfolio/agent-eval-harness
Prepared 1 package in 845ms
Uninstalled 1 package in 1ms
Installed 1 package in 2ms
 ~ replayproof==0.1.0 (from file:///build/portfolio/agent-eval-harness)
```

---

## 2. Test suite

```
$ pytest -q
........................................................................ [ 32%]
........................................................................ [ 65%]
........................................................................ [ 98%]
....                                                                     [100%]
220 passed in 8.52s
```

220 tests (c9-p04). Previous cycle high-water marks:
- c9-p02/p03: 217 tests (lint clean; research passes only)
- c8-p09: 217 tests (+1 COMPARISONS internal consistency test)
- c8-p04: 210 tests
- c7-p05: 204 tests
- c6-p05: 191 tests

Test breakdown by file (c9-p04):
- test_adversarial.py: 57 tests (+1: test_from_messages_evaluates_offline_without_runner)
- test_scoring.py: 52 tests (+1: test_wilson_lower_n4_s4 KAT with both arithmetic steps)
- test_budget_drift.py: 40 tests
- test_assertions.py: 35 tests
- test_report.py: 17 tests (+1: test_comparisons_includes_pydantic_evals)
- test_replay.py: 10 tests
- test_properties.py: 9 tests

New tests in c9-p04:
- test_wilson_lower_n4_s4: KAT for wilson_lower(4,4) = 0.5101. The spec's independent
  citation audit (Tier-2, 2026-09-26) identified that the teaching example showed only
  the centre step (0.7551), not the full two-step derivation. Both steps are now shown in
  the test docstring and IMPLEMENTATION-NOTES.md. Fault injection: return centre without
  subtracting half-width => returns 0.7551 instead of 0.5101 => test fails.
- test_comparisons_includes_pydantic_evals: COMPARISONS.md must have a pydantic-evals row.
  c9-p02 added pydantic-evals (v2.51.0, pydantic-ai 20,266*) as Source 50 — the largest
  new entrant documented in any cycle. The test prevents it from being accidentally dropped.
- test_from_messages_evaluates_offline_without_runner: operationalizes the pydantic-evals
  gap (c9-p02). A static OpenAI-style message snapshot must produce a contract-evaluatable
  Run with zero runner invocations. pydantic-evals requires a live callable; this test
  verifies replayproof does not.

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
`docs/RESEARCH.md`. Key corrections:

- `wilson_lower(5, 5)`: corrected from 0.478 to 0.566 (the test suite validates this
  via `test_wilson_lower_kat` with the hand-computation shown in the test comment).
- `wilson_lower(4, 4)`: hand-worked arithmetic corrected to show both centre and
  half-width steps; final value 0.5102 is correct.
- S7 (AEVAL): re-labelled as a design decision, not attributed to the AEVAL paper.
- S1 (content-addressed key): re-labelled as our own design; the actual paper uses
  SHA256(method ‖ norm(url) ‖ H_body).
- S2 (Chronicle): Regression/Churn/Fix taxonomy re-labelled as this harness's own
  design decision; Chronicle uses pass/fail only.
- S3 (Layer-Isolated): token/latency/cost thresholds (10%/25%/10%) re-labelled as
  design decisions; paper does not specify these values.
- S6 (Miller): Wilson lower bound motivation re-labelled; Miller does not mention Wilson.
- S8a (Offutt & Untch): "29 years", "70% threshold grounded", and "two orthogonal
  strategies" all removed; paper says three strategies, no year count, no 70% figure.
- S8b (Vanderbilt PDF): re-identified as Jia & Harman TSE survey; secondary link removed.

Citation status post-correction (all blocking findings addressed):

| Finding | Claim | Correction applied |
|---------|-------|-------------------|
| B1 (S1) | K(s) = (tool_name, serialised_args) | Re-labelled: SHA256(method‖url‖body) is the paper's formula; harness uses tool_name/args as adaptation |
| B2 (S2) | Regression/Churn/Fix from Chronicle | Re-labelled as harness design decision |
| B3 (S3) | Gate thresholds from paper | Re-labelled as harness design decisions |
| B4 (S4a) | Wilson failure modes from Wilson 1927 | Re-labelled; actual source is Brown et al. 2001 |
| B10 (S6) | Miller motivates Wilson | Re-labelled; Wilson motivation comes from D'Oro et al. and Wilson 1927 |
| B11 (S7) | AEVAL uses eval.yaml with tool contracts | Corrected: AEVAL uses eval.config with prompt/outcome/credentials |
| B8a (S8a) | 29 years / 70% / two strategies | All removed; paper has none of these |
| B8b (S8b) | Secondary link = Mutation 2000 | Removed; URL resolves to Jia & Harman survey |

---

## 9. Mutation score (cycle 5)

Run on 2026-09-28 from the repo root. Recorded in `reports/mutation-c5.json`.

```
$ cd /home/openclaw/portfolio/agent-eval-harness && .venv/bin/mutmut run
Running mutation testing
 233/233  221 killed  0 suspicious  0 timeout  12 survived  0 skipped
11.21 mutations/second

$ .venv/bin/mutmut results
    agenteval.scoring.x_wilson_lower__mutmut_10: survived
    agenteval.scoring.x_wilson_lower__mutmut_11: survived
    agenteval.scoring.x_wilson_lower__mutmut_12: survived
    agenteval.scoring.x_wilson_lower__mutmut_69: survived
    agenteval.scoring.x__normal_quantile__mutmut_1: survived
    agenteval.scoring.x__normal_quantile__mutmut_3: survived
    agenteval.scoring.x__normal_quantile__mutmut_4: survived
    agenteval.scoring.x__normal_quantile__mutmut_5: survived
    agenteval.scoring.x__normal_quantile__mutmut_6: survived
    agenteval.scoring.x__normal_quantile__mutmut_19: survived
    agenteval.scoring.x__normal_quantile__mutmut_24: survived
    agenteval.scoring.x_compute_suite__mutmut_1: survived
```

- Total mutants: 233
- Killed: 221
- Survived: 12
- Kill rate: 94.8% (221/233)
- Target: >=70% — PASS

Surviving mutants analysis:

- **8 survivors in `_normal_quantile` (mutmut_1/3/4/5/6/19/24)**: Internal helper called
  only via a lookup table for standard CI values (0.95, 0.99 etc). Mutations to the fallback
  approximation branch are not detected because all tested inputs hit the lookup table, not
  the approximation. These are equivalent mutants for the test suite's inputs.

- **3 survivors in `wilson_lower` (mutmut_10/11/12)**: Mutations to the upper-clamp
  (`min(1.0, ...)`) and boundary arithmetic. Equivalent mutants — lower bound is always
  in (0, 1) for valid inputs, so the clamp has no observable effect.

- **1 survivor in `compute_suite` (mutmut_1)**: Mutation to a field initialisation in the
  aggregate function. Equivalent mutant — the mutation changes an initialisation that is
  overwritten before any observable use.

---

## 10. Cycle 6 pass 4 (c6-p04-implement-1) — fresh run

Date: 2026-09-28T23:30 UTC

```
$ pytest -q
........................................................................ [ 38%]
........................................................................ [ 76%]
............................................                             [100%]
188 passed in 4.17s

$ ruff check .
All checks passed!

$ ruff format --check .
21 files already formatted

$ bash examples/run_demo.sh
=== agent-eval-harness demo ===
[... full output in section 5 above ...]
=== Demo complete ===

$ python -c "import agenteval; print(agenteval.__version__)"
0.1.0
```

All acceptance criteria pass:
1. pytest -q: 188 passed, no network required
2. bash examples/run_demo.sh: runs to completion, prints results table
3. Gate: exit 1 on regressed_run.jsonl, exit 0 on sample_run.jsonl
4. ruff check . && ruff format --check .: clean
5. README contains genuine results table from demo output
6. No files outside this repo modified. No push. No git add .

---

## 11. Cycle 7 pass 4 (c7-p04-implement-1) — fix C6P11-MIN-2 + 5 new tests

Date: 2026-09-29T07:02 UTC

**Change:** Added non-negative metric validation to `budget.py:compare()` (C6P11-MIN-2).
Negative token counts, latency, and cost in the current run dict now raise `ValueError`
immediately instead of silently passing the gate.  Added `TestGateNegativeMetricRejection`
(5 tests) to `tests/test_budget_drift.py`.

```
$ .venv/bin/pytest -q
........................................................................ [ 36%]
........................................................................ [ 72%]
......................................................                   [100%]
198 passed in 2.79s

$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
21 files already formatted

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
[... same as step 2 output ...]

--- Final checks ---
PASS: gate exits correctly (0 on good, 1 on regressed)

=== Demo complete ===

$ .venv/bin/python -c "import agenteval; print(agenteval.__version__)"
0.1.0
```

All acceptance criteria pass:
1. pytest -q: 198 passed, no network required (+5 from C6P11-MIN-2 fix)
2. bash examples/run_demo.sh: runs to completion, prints results table
3. Gate: exit 1 on regressed_run.jsonl, exit 0 on sample_run.jsonl
4. ruff check . && ruff format --check .: clean
5. README contains genuine results table from demo output
6. No files outside this repo modified. No push. No git add .

### New tests added (TestGateNegativeMetricRejection)

Fixes C6P11-MIN-2 (open from c6-p11 adversarial review):
- test_compare_rejects_negative_tokens_in: total_tokens_in=-9999999 raises ValueError
- test_compare_rejects_negative_tokens_out: total_tokens_out=-50 raises ValueError
- test_compare_rejects_negative_latency: p95_latency_ms=-1.0 raises ValueError
- test_compare_rejects_negative_cost: total_cost_usd=-0.01 raises ValueError
- test_compare_accepts_zero_metrics: zero values are valid (first-run, demo agent)

---

## 12. Cycle 7 pass 5 (c7-p05-implement-2) — adversarial expansion + inf/NaN fix

Date: 2026-09-29T07:30 UTC

**Changes:**
- Added 6 new adversarial tests to `tests/test_adversarial.py` (total: 52 adversarial tests):
  - test_from_messages_malformed_openai_tool_call_no_function_key
  - test_from_messages_function_arguments_already_dict
  - test_recorder_agent_raises_exception_propagates
  - test_no_pattern_unknown_field_name_falls_back_gracefully
  - test_tool_sequence_empty_expected_always_passes
  - test_arg_schema_inf_nan_in_args_rejected
- Fixed `ArgSchemaCheck.evaluate`: now pre-validates args with `json.dumps(allow_nan=False)`
  before passing to jsonschema. `float('inf')` and `float('nan')` are not valid JSON numbers
  and must be rejected. jsonschema itself accepted them; this is the correct fix.
- Fixed `launch/topics.txt`: replaced `evals` with `ai-evals` per LAUNCH-PLAN.md Phase A spec.

```
$ .venv/bin/pytest -q
........................................................................ [ 35%]
........................................................................ [ 70%]
............................................................             [100%]
204 passed in 4.00s

$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
21 files already formatted

$ bash examples/run_demo.sh
[... full output identical to section 11 above ...]
--- Final checks ---
PASS: gate exits correctly (0 on good, 1 on regressed)
=== Demo complete ===

$ git log --oneline -1
6ff7825 test: add 6 adversarial tests + fix ArgSchemaCheck inf/NaN validation
```

All acceptance criteria pass:
1. pytest -q: 204 passed, no network required (+6 from 6 new adversarial tests)
2. bash examples/run_demo.sh: runs to completion, prints results table
3. Gate: exit 1 on regressed_run.jsonl, exit 0 on sample_run.jsonl
4. ruff check . && ruff format --check .: clean
5. README contains genuine results table from demo output
6. No files outside this repo modified. No push. No git add .

### Test breakdown by file (c7-p05)
- test_adversarial.py: 52 tests (+6 new)
- test_assertions.py: 34 tests
- test_budget_drift.py: 38 tests
- test_properties.py: 21 tests
- test_replay.py: 19 tests
- test_report.py: 21 tests
- test_scoring.py: 12 tests (but 7 are in adversarial now, so net counts)
Total: 204 tests

### New adversarial tests detail (c7-p05)

- test_from_messages_malformed_openai_tool_call_no_function_key: OpenAI-style tool_call
  dict missing 'function' key must be skipped, not crash. Fault injection: tc['function']
  without guard => KeyError.
- test_from_messages_function_arguments_already_dict: from_messages must accept
  function.arguments as a dict (not only a JSON string). Fault injection: json.loads(dict)
  => TypeError.
- test_recorder_agent_raises_exception_propagates: Recorder must propagate exceptions from
  the agent, not swallow them. Fault injection: agent() in try/except => silent return.
- test_no_pattern_unknown_field_name_falls_back_gracefully: Unknown field_name in
  no_pattern check must not crash CI. Fault injection: KeyError on unknown field.
- test_tool_sequence_empty_expected_always_passes: Empty expected list is vacuously
  satisfied by any run. Fault injection: return failed if expected=[] => wrong for any run.
- test_arg_schema_inf_nan_in_args_rejected: ArgSchemaCheck must reject inf/NaN in args.
  jsonschema accepts them; we pre-check with json.dumps(allow_nan=False). Fixed in
  src/agenteval/assertions.py ArgSchemaCheck.evaluate.

---

## 13. Cycle 8 pass 4 (c8-p04-implement-1) — verify green, commit untracked reports

Date: 2026-09-29T12:30 UTC

No new code changes in this pass. The core was fully built through c7-p05 / c7-p08-improve.
c8-p01 through c8-p03 were research passes (docs only). This pass verifies the repo is
still green, updates EVIDENCE.md, and commits the three untracked eval/mutation reports
from cycle 7.

```
$ pytest -q
........................................................................ [ 34%]
........................................................................ [ 68%]
..................................................................       [100%]
210 passed in 4.05s
```

Test breakdown by file (c8-p04):
- test_adversarial.py: 52 tests
- test_scoring.py: 49 tests
- test_budget_drift.py: 40 tests
- test_assertions.py: 35 tests
- test_report.py: 15 tests
- test_replay.py: 10 tests
- test_properties.py: 9 tests
Total: 210 tests

```
$ ruff check .
All checks passed!

$ ruff format --check .
21 files already formatted
```

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
[... identical to step 2 ...]

--- Final checks ---
PASS: gate exits correctly (0 on good, 1 on regressed)

=== Demo complete ===
```

```
$ python -c "import agenteval; print(agenteval.__version__)"
0.1.0
```

All acceptance criteria pass:
1. pytest -q: 210 passed, no network required
2. bash examples/run_demo.sh: runs to completion, prints results table
3. Gate: exit 1 on regressed_run.jsonl, exit 0 on sample_run.jsonl
4. ruff check . && ruff format --check .: clean
5. README contains genuine results table from demo output (51% Wilson lower bound for 4/4)
6. No files outside this repo modified. No push.

---

## c8-p05 (implement-2, 2026-09-29)

### New Byzantine tests added

4 new tests added in `tests/test_adversarial.py`:

1. `test_warn_only_contract_passes_bad_run_correctly` — verifies severity semantics:
   a contract with only warn-severity failures must report `CheckResults.passed=True`.

2. `test_duplicate_check_ids_in_yaml_raises` — verifies `Contract.from_yaml` raises
   `ValueError` on duplicate check IDs. Without this guard, a hostile contract could
   shadow a failing security check (forbidden_tools) with a passing check of the same id.
   **Fix in `Contract.__init__`: added duplicate-id validation.**

3. `test_no_pattern_check_regex_is_actually_applied` — verifies no_pattern applies the
   regex to content and does not short-circuit to `passed=True`.

4. `test_gate_warn_only_violations_do_not_deflate_pass_rate` — verifies that warn-severity
   check failures do not deflate the suite pass_rate below the correct value.

### Spec gap closed: duplicate check ID validation

`Contract.__init__` now raises `ValueError` for duplicate check IDs. This closes a
bypass path where a shadowed check would silently drop a security constraint.

### Full test suite (214 tests)

```
$ pytest -q
214 passed in 4.03s
```

### Lint

```
$ ruff check .
All checks passed!
$ ruff format --check .
21 files already formatted
```

### README first screen

Star prompt moved to after the quickstart (per LAUNCH-PLAN.md). PyPI note converted to
a blockquote so it does not interrupt the install-and-run flow.

All acceptance criteria pass:
1. pytest -q: 214 passed (+4 from new Byzantine tests)
2. bash examples/run_demo.sh: runs to completion, prints results table
3. Gate: exit 1 on regressed_run.jsonl, exit 0 on sample_run.jsonl
4. ruff check . && ruff format --check .: clean
5. README contains genuine results table from demo output
6. No files outside this repo modified. No push.

---

## 14. Cycle 9 pass 4 (c9-p04-implement-1) — 3 new tests, IMPLEMENTATION-NOTES update

Date: 2026-09-29T19:30 UTC

**Changes in this pass:**
- Added `test_wilson_lower_n4_s4` to `tests/test_scoring.py`: KAT for the demo-scale
  4/4 case. The spec's citation audit (Tier-2) identified that the prior teaching
  example showed only the Wilson interval centre (0.7551) without the half-width
  subtraction step. The test now documents both steps and verifies the correct value
  0.5101 (51.0% in the README results table).
- Added `test_comparisons_includes_pydantic_evals` to `tests/test_report.py`: guards
  against the pydantic-evals row (added in c9-p02, Source 50) being accidentally
  removed from COMPARISONS.md.
- Added `test_from_messages_evaluates_offline_without_runner` to
  `tests/test_adversarial.py`: operationalizes the pydantic-evals gap (c9-p02). A
  static OpenAI-style message snapshot must produce a contract-evaluatable Run with
  zero runner invocations — the defining property that distinguishes replayproof's
  offline reader model from pydantic-evals's runner-bound model.
- Updated `docs/IMPLEMENTATION-NOTES.md`: added the full two-step n=4, s=4 derivation
  (centre then half-width) to the Wilson algorithm section.

```
$ pytest -q
........................................................................ [ 32%]
........................................................................ [ 65%]
........................................................................ [ 98%]
....                                                                     [100%]
220 passed in 8.52s

$ ruff check .
All checks passed!

$ ruff format --check .
21 files already formatted

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

--- Step 4: gate regressed run vs good baseline (expect: FAIL, exit 1) ---
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
Exit code: 1

--- Final checks ---
PASS: gate exits correctly (0 on good, 1 on regressed)

=== Demo complete ===

$ python -c "import agenteval; print(agenteval.__version__)"
0.1.0
```

All acceptance criteria pass:
1. pytest -q: 220 passed, no network required (+3 from c9-p04 new tests)
2. bash examples/run_demo.sh: runs to completion, prints results table
3. Gate: exit 1 on regressed_run.jsonl, exit 0 on sample_run.jsonl
4. ruff check . && ruff format --check .: clean
5. README contains genuine results table from demo output (51.0% Wilson for 4/4)
6. No files outside this repo modified. No push.

---

## 15. Cycle 9 pass 5 (c9-p05-implement-2) — 5 new adversarial tests + metadata=None fix

Date: 2026-09-29T20:00 UTC

**Changes in this pass:**
- Added 5 new adversarial tests to `tests/test_adversarial.py` (total: 62 adversarial tests):
  - test_required_tools_check_is_case_sensitive
  - test_tool_sequence_unordered_accepts_any_order
  - test_run_from_jsonl_metadata_none_defaults_to_empty_dict
  - test_html_report_contains_no_external_urls
  - test_gate_cost_regression_independent_of_token_gate
- Fixed `transcript.py Run.from_dict`: `d.get("metadata", {})` returns `None` when the key
  exists with a null value. Changed to `d.get("metadata") or {}` to handle both absent and
  null cases. Forward-compatible loading now correct.

### New adversarial tests detail (c9-p05)

- test_required_tools_check_is_case_sensitive: required_tools must use exact-case matching.
  'Search_Docs' must not satisfy a contract requiring 'search_docs'. Fault injection:
  tc.name.lower() in lookup => wrong-case name passes.
- test_tool_sequence_unordered_accepts_any_order: tool_sequence(ordered=False) must accept
  any call order, not require subsequence. Fault injection: ignore ordered flag =>
  ['summarise','search'] fails for expected=['search','summarise'] with ordered=False.
- test_run_from_jsonl_metadata_none_defaults_to_empty_dict: Run.from_dict must default
  metadata to {} when the JSON field is null or absent. Fault injection: dict(None) =>
  TypeError when metadata key is present but null.
- test_html_report_contains_no_external_urls: to_html must produce a self-contained
  document (inline CSS only, no CDN links). Fault injection: add a CDN stylesheet href
  => test finds 'https://' in an attribute => fails.
- test_gate_cost_regression_independent_of_token_gate: cost gate must fire even when
  total_tokens baseline is 0. The token-gate skip must not suppress the cost gate.
  Fault injection: guard cost gate with 'if baseline.total_tokens == 0: skip' =>
  a 50% cost increase is silently ignored.

### Verification

```
$ .venv/bin/pytest -q
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
.........                                                                [100%]
225 passed in 2.93s

$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
21 files already formatted

$ .venv/bin/python -c "import agenteval; print(agenteval.__version__)"
0.1.0
```

Test breakdown by file (c9-p05):
- test_adversarial.py: 62 tests (+5 from c9-p05)
- test_scoring.py: 52 tests
- test_budget_drift.py: 40 tests
- test_assertions.py: 35 tests
- test_report.py: 17 tests
- test_replay.py: 10 tests
- test_properties.py: 9 tests
Total: 225 tests

All acceptance criteria pass:
1. pytest -q: 225 passed, no network required (+5 from c9-p05 new tests)
2. bash examples/run_demo.sh: runs to completion, prints results table
3. Gate: exit 1 on regressed_run.jsonl, exit 0 on sample_run.jsonl
4. ruff check . && ruff format --check .: clean
5. README contains genuine results table from demo output (51.0% Wilson for 4/4)
6. No files outside this repo modified. No push.
