# docs/IMPLEMENTATION-NOTES.md — Spec Traceability

This document maps every core algorithm to the equation or reference that defines it,
the source file and function that implements it, and the test that validates the
implementation is correct.

Format: `Reference → src/path:function → test that validates it`

---

## 1. Wilson Score Confidence Interval Lower Bound

**Reference:** Wilson, E. B. (1927). "Probable inference, the law of succession,
and statistical inference." *JASA* 22(158): 209–212.
(Secondary: https://www.statisticshowto.com/wilson-ci/)

**Equation:**

    w_lower = (p_hat + z^2/(2n) - z * sqrt(p_hat*(1-p_hat)/n + z^2/(4n^2)))
              / (1 + z^2/n)

    where:
        p_hat = successes / n       (observed proportion)
        z     = 1.959963985         (two-sided 95% normal quantile)
        n     = total trials

**Implementation:** `src/agenteval/scoring.py:wilson_lower`

Key lines (verbatim mapping):
```python
z2 = z * z
n2 = n * n
term_under_root = p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n2)
numerator = p_hat + z2 / (2.0 * n) - z * math.sqrt(term_under_root)
denominator = 1.0 + z2 / n
lower = numerator / denominator
return max(0.0, min(1.0, lower))
```

**Test that validates it:** `tests/test_scoring.py:TestWilsonLower.test_wilson_lower_n100_s90`
(also `test_wilson_lower_n4_s4` for the demo-scale 4/4 case with both arithmetic steps)

Hand-computed verification at n=100, s=90:
```
p_hat     = 0.90
z         = 1.959963985
z^2       = 3.84145882
term      = 0.90*0.10/100 + 3.84145882/40000 = 0.0009 + 0.0000960 = 0.0009960
sqrt(t)   = 0.031559...
numerator = 0.90 + 0.019207 - 1.959964*0.031559 = 0.90 + 0.019207 - 0.061854 = 0.857353
denom     = 1 + 3.84145882/100 = 1.038416
lower     = 0.857353 / 1.038416 = 0.82566
```
Expected: 0.82566 ± 0.005. Verified against scipy.stats.proportion_confint reference value 0.8257.

Hand-computed verification at n=4, s=4 (the demo-scale 4/4 case):
```
p_hat     = 1.0
z         = 1.959963985
z^2       = 3.841459

Step 1 — centre (without half-width):
  numerator₀ = 1.0 + z²/(2·4) = 1.0 + 0.480182 = 1.480182
  denom      = 1 + z²/4        = 1 + 0.960365  = 1.960365
  centre     = 1.480182 / 1.960365 = 0.75504

Step 2 — half-width:
  term       = 1.0·0.0/4 + z²/(4·16) = 0 + 0.060023 = 0.060023
  half_num   = z·√0.060023 = 1.959964·0.245000 = 0.480190
  half       = 0.480190 / 1.960365 = 0.24496

Step 3 — lower bound:
  lower      = centre − half = 0.75504 − 0.24496 = 0.51008 ≈ 0.5101
```
Expected: ~0.5101 (reports as 51.0% in README). The intermediate value 0.7551 is the
Wilson interval centre, not the lower bound — the spec citation audit (Tier-2, 2026-09-26)
identified presenting only step 1 as a teaching artifact error.

**Hypothesis property tests:** `tests/test_properties.py:test_wilson_lower_monotone_in_successes`
(tests monotonicity property; `test_wilson_lower_in_unit_interval` tests range constraint)

---

## 2. Pass Rate

**Reference:** Definition of a sample proportion (introductory statistics).

**Equation:** `pass_rate = successes / n`  where `successes = |{r : r.passed == True}|`

**Implementation:** `src/agenteval/scoring.py:pass_rate`

**Test that validates it:** `tests/test_scoring.py:TestPassRate.test_pass_rate_mixed`
(asserts 3/5 = 0.6 explicitly; `test_pass_rate_all_pass` asserts 5/5 = 1.0)

**Hypothesis property test:** `tests/test_properties.py:test_pass_rate_definition`

---

## 3. Percentile (p50 / p95 latency)

**Reference:** Linear interpolation nearest-rank percentile — standard definition.

**Equation:**
```
idx   = (p / 100) * (n - 1)
lower = floor(idx)
upper = min(lower + 1, n - 1)
frac  = idx - lower
result = values[lower] * (1 - frac) + values[upper] * frac
```

**Implementation:** `src/agenteval/scoring.py:_percentile`

**Test that validates it:** `tests/test_scoring.py:TestPercentile.test_percentile_p50_even`

Hand computation: for `[10, 20, 30, 40]` at p=50:
```
idx = 0.5 * 3 = 1.5
lower = 1, upper = 2, frac = 0.5
result = 20.0 * 0.5 + 30.0 * 0.5 = 25.0
```
Expected: 25.0. Test asserts exact equality.

---

## 4. Dry Replay — Byte-Identical Round-Trip

**Reference:** Mudasiru (2026), arxiv 2607.16200 — replay fidelity F=1.0 in dry mode.

**Invariant:** `Run.to_jsonl(replay(run, {}, mode="dry")) == run.to_jsonl()`

**Implementation:** `src/agenteval/replay.py:replay` (dry branch copies tool call objects unchanged)

**Test that validates it:** `tests/test_replay.py:TestDryReplay.test_dry_replay_byte_identical`

The test constructs a Run, dry-replays it, serialises both, and asserts string equality.
The Hypothesis property test `tests/test_properties.py:test_dry_replay_idempotent`
additionally verifies the second replay is also identical.

---

## 5. Strict Replay — ReplayMismatch on Divergence

**Reference:** The spec definition in `replay.py` module docstring; Cut-Point Replay
paper (arxiv 2609.20625).

**Invariant:** If `tool_fn(**recorded_args) != recorded_result`, raise `ReplayMismatch`
with `.expected = recorded_result` and `.actual = tool_fn(**recorded_args)`.

**Implementation:** `src/agenteval/replay.py:replay` (strict branch, lines 65-75 approx)

**Test that validates it:** `tests/test_replay.py:TestStrictReplay.test_strict_mode_raises_on_mismatch`
and `test_replay_mismatch_carries_expected_actual`

---

## 6. Tool Sequence Check — Subsequence Match

**Reference:** Spec requirement: `tool_sequence(expected, ordered=True)` — subsequence match.

**Algorithm:** Greedy linear scan. For each expected name, advance a pointer through the
actual names until a match is found. If the pointer reaches the end without finding the
name, fail.

**Implementation:** `src/agenteval/assertions.py:ToolSequenceCheck.evaluate`

**Test that validates it:** `tests/test_assertions.py:TestToolSequenceCheck`
- `test_passes_on_correct_sequence`: correct order passes
- `test_fails_on_wrong_order`: reversed order fails (strict)
- `test_unordered_mode_passes_despite_order`: reversed order passes in unordered mode

---

## 7. Arg Schema Check — JSON Schema Validation

**Reference:** JSON Schema Draft-07 specification at https://json-schema.org/specification.
External standard; validation delegated to the `jsonschema` library.

**Implementation:** `src/agenteval/assertions.py:ArgSchemaCheck.evaluate`

**Test that validates it:** `tests/test_assertions.py:TestArgSchemaCheck`
- `test_passes_on_valid_args`: valid args against schema
- `test_fails_on_invalid_args`: missing required key fails validation

---

## 8. No-Pattern Check — PII Detection

**Reference:** EACL 2026 "Personal Information Parroting" (arxiv 2602.20580) — email and
phone regex patterns.

**PII patterns (in `assertions.py:PII_PATTERNS`):**
- email: `[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}`
- us_phone: `(\+?1[\s\-.]?)?(\(?\d{3}\)?[\s\-.]?)?\d{3}[\s\-.]?\d{4}`
- us_ssn: `\d{3}-\d{2}-\d{4}`
- credit_card: `(\d{4}[\s\-]?){3}\d{4}`

**Implementation:** `src/agenteval/assertions.py:NoPatternCheck.evaluate`

**Test that validates it (hostile-user case):** `tests/test_assertions.py:TestNoPatternCheck.test_fails_on_email_match`

This test is explicitly the hostile-user case per the spec: an email address is present
in the final content and must trigger the check. A naive implementation that applies
`field_name` incorrectly or compiles the regex wrong would fail this test.

---

## 9. Budget Gate — Regression Detection

**Reference:** "Gating the Deterministic Scaffold" (arxiv 2606.11686). The gate compares
four metrics against configurable tolerances.

**Equations:**
```
pass_rate_drop = baseline.pass_rate - current.pass_rate
token_increase = (current_tokens - baseline_tokens) / baseline_tokens
latency_increase = (current_p95 - baseline_p95) / baseline_p95
cost_increase = (current_cost - baseline_cost) / baseline_cost
```
Gate trips if any metric exceeds its threshold.

**Implementation:** `src/agenteval/budget.py:compare`

**Test that validates it:** `tests/test_budget_drift.py:TestBudgetGate`
- `test_gate_trips_on_pass_rate_drop`: pass rate 0.9 -> 0.7 trips with threshold 0.0
- `test_gate_trips_on_token_increase`: 50% increase trips with 10% threshold
- `test_gate_ok_on_tokens_within_tolerance`: 5% increase passes with 10% threshold
- `test_gate_passes_identical_inputs`: same suite vs itself always passes

---

## 10. Drift Classification

**Reference:** Cut-Point Replay paper (arxiv 2609.20625) — regression vs churn distinction.

**Classification rules:**
```
a_passed=True,  b_passed=False  -> regression
a_passed=False, b_passed=True   -> fix
a_passed=False, b_passed=False, a_reason != b_reason -> churn
a_passed=True,  b_passed=True   -> stable_pass
a_passed=False, b_passed=False, a_reason == b_reason -> stable_fail
```

**Implementation:** `src/agenteval/drift.py:drift`

**Test that validates it:** `tests/test_budget_drift.py:TestDrift`
- `test_drift_detects_regression`: catches misclassification as churn
- `test_drift_classifies_fix`: catches inverted logic
- `test_drift_churn_both_fail_different_reason`: catches stable_fail vs churn confusion

---

## Spec Coverage Summary

| Spec requirement | Implemented in | Validated by |
| --- | --- | --- |
| transcript.py frozen dataclasses | transcript.py | test_budget_drift.py:TestTranscriptRoundTrip |
| record.py Recorder + clock injection | record.py | test_replay.py (uses Recorder indirectly) |
| replay.py dry/strict/lenient modes | replay.py | test_replay.py |
| assertions.py all 10 check types | assertions.py | test_assertions.py |
| scoring.py wilson_lower | scoring.py:wilson_lower | test_scoring.py:TestWilsonLower |
| scoring.py pass_rate | scoring.py:pass_rate | test_scoring.py:TestPassRate |
| scoring.py compute_suite | scoring.py:compute_suite | test_scoring.py:TestComputeSuite |
| budget.py gate | budget.py:compare | test_budget_drift.py:TestBudgetGate |
| drift.py verdict classification | drift.py:drift | test_budget_drift.py:TestDrift |
| report.py markdown stable | report.py:to_markdown | test_report.py:TestMarkdownReport |
| report.py html self-contained | report.py:to_html | test_report.py:TestHTMLReport |
| cli.py all 6 commands | cli.py | run_demo.sh (integration) |

All spec acceptance criteria are covered by at least one test.
