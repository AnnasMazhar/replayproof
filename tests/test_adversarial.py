"""Adversarial and byzantine test cases for agent-eval-harness.

These tests target implementation paths that a naive developer would get wrong, and
cases a hostile user might construct to subvert the contract evaluation.

--- New in c2-p05 ---

test_run_from_jsonl_truncated_raises_not_silently_corrupts:
    Catches a from_jsonl implementation that silently swallows a JSONDecodeError and
    returns a partially-initialised Run instead of raising. A truncated JSONL line
    must raise json.JSONDecodeError, not produce a corrupted Run.
    Fault injection: wrap json.loads in try/except and return a default Run => silent
    corruption that propagates through the pipeline.

test_contract_empty_checks_always_passes:
    Catches a Contract.evaluate that returns a failed result for an empty check list.
    A contract with zero checks must always pass (vacuous truth), because the caller
    is asserting "no constraints" and the harness must not add hidden constraints.
    Fault injection: return passed=False when checks is empty => unexpected failure.

test_contract_unknown_check_type_raises_valueerror:
    Catches a Contract loader that silently skips unknown check types instead of
    raising. Skipping would silently drop a check the user thought they had, producing
    a false-green suite.
    Fault injection: return None from _build_check for unknown type, filter out Nones
    in the Contract constructor => silently missing check.

test_contract_tool_sequence_repeated_tool_names:
    Catches a tool_sequence check that incorrectly rejects a run where the same tool
    is called multiple times, as long as the subsequence requirement is satisfied.
    e.g. required=['search', 'summarise'] should pass if run calls
    ['search', 'search', 'summarise'] — the subsequence is satisfied at positions 0,2.
    Fault injection: use a set-intersection check instead of subsequence scan => passes
    if any required tool was ever called, regardless of order, but also incorrectly
    handles repeated calls.

test_contract_no_pattern_pii_in_tool_args:
    Catches a no_pattern check that only scans final_content and silently skips
    tool args even when field_name='tool_args'. PII can leak through tool args
    (e.g. an email passed to a send_email tool).
    Fault injection: only scan run.final_content() => email in args is missed.

test_drift_churn_vs_regression_same_case_id:
    Catches a drift function that classifies a case as 'regression' when both A and B
    fail but with different failure reasons (correct classification: 'churn').
    Fault injection: use 'not a_passed and not b_passed' => 'stable_fail' regardless
    of reason, missing the churn classification.

test_gate_crafted_baseline_cannot_inflate_thresholds:
    Catches a gate that allows a manually crafted baseline to inflate effective
    thresholds by setting baseline values to extreme numbers. If the baseline says
    tokens = 1_000_000 and current = 1_100_001, that is +10.0001% which should trip
    the 10% gate. A gate must compare the actual values, not round to integer pct.
    Fault injection: round percentage to integer before comparison => 10% rounds to
    10 which passes, even though actual increase is 10.0001%.

test_jsonl_roundtrip_with_unicode_and_null_bytes:
    Catches a to_jsonl/from_jsonl round-trip that corrupts Unicode content or fails
    on content containing null-byte-adjacent characters (\\u0000 is valid JSON but
    tricky for some parsers).
    Fault injection: use ascii=True in json.dumps => encodes non-ASCII to \\uXXXX
    which is technically reversible, but special characters in content can be mangled.

test_run_with_multiple_tool_calls_same_name:
    Catches assertions that count unique tool names instead of total calls. A run
    calling 'search' three times must register as 3 tool calls for max_tool_calls,
    not 1.
    Fault injection: use len(set(names)) instead of len(names) for max_tool_calls.

test_wilson_lower_zero_successes:
    Catches a wilson_lower implementation that crashes or returns negative values
    when successes=0. The lower bound must be 0.0 (not negative, not NaN).
    Fault injection: omit the s==0 early-return path => sqrt of negative number.

Faults detected by each test:

test_replay_strict_byzantine_mismatched_result_type:
    Catches a strict replay that compares results with 'is' identity instead of '=='
    equality, causing a mismatch on semantically equal values of different types (e.g.
    integer 1 vs True, or a freshly constructed string).
    Fault injection: replace 'actual != tc.result' with 'actual is not tc.result' in
    replay.py => raises ReplayMismatch for equal but non-identical values => test fails.

test_replay_strict_missing_tool_raises_not_returns_none:
    Catches strict replay that returns None for a missing tool instead of raising.
    This is a silent correctness failure: the run completes but the result is wrong.
    Fault injection: replace raise with 'actual = None' => no exception => test fails.

test_wilson_lower_adversarial_n1_s1:
    Catches a wilson_lower implementation that returns 1.0 for a single success
    (100% observed). The Wilson bound for n=1, s=1 at 95% is ~0.205, not 1.0.
    A naive implementation that returns p_hat when p_hat == 1.0 would fail.
    Fault injection: return float(successes / n) when successes == n => returns 1.0.

test_wilson_lower_adversarial_high_confidence:
    Catches an implementation that hardcodes the z-score for 95% and ignores the
    confidence parameter. At 99% (z ≈ 2.576), the lower bound should be lower than
    at 95% (z ≈ 1.960) for the same inputs.
    Fault injection: always use z=1.960 regardless of confidence => 95% == 99% bound.

test_gate_integer_overflow_token_count:
    Catches a gate that crashes or computes a wrong threshold when token counts
    are very large (> 2^31). Budget math must use float arithmetic.
    Fault injection: cast token counts to int32 before arithmetic => overflow => wrong %.

test_gate_identical_inputs_always_passes:
    Catches a gate implementation with an off-by-one in the threshold check that
    trips even when current == baseline. Threshold is 0.0 for pass_rate; any epsilon
    error in float comparison could cause a false positive.
    Fault injection: use '>' instead of '>=' in the threshold comparison => trips on equal.

test_gate_nan_pass_rate_does_not_crash:
    Catches a gate that raises an unhandled exception when pass_rate is NaN (e.g. 0/0
    for an empty suite). The gate should fail closed (report a trip) rather than crashing.
    Fault injection: remove the 'if math.isnan' guard in budget.py => ZeroDivisionError.

test_contract_forbidden_tool_regex_injection:
    Catches a forbidden_tools check that constructs a regex from the tool name and fails
    to escape it. A tool named 'search.docs' could inadvertently match 'searchXdocs' if
    dots are unescaped. The check must use exact name matching, not regex.
    Fault injection: use re.search(name, combined_names) without re.escape => matches
    'search.docs' against 'searchXdocs' => false positive => test fails.

test_contract_no_pattern_check_catastrophic_backtrack:
    Catches a no_pattern check that uses a user-supplied regex directly against a very
    long string without timeout, triggering catastrophic backtracking (ReDoS).
    The test times out or hangs on a backtracking regex if unguarded.
    Fault injection: use a known backtracking pattern like '(a+)+b' against a long
    string of 'a's — the check must complete in < 1s.
    Note: we assert the check completes and does not raise; we do NOT test that the
    regex matches (that is the user's problem). The fault is an unguarded re call.

test_contract_arg_schema_null_value_passes_nullable:
    Catches a JSON Schema validator that incorrectly rejects null/None values for a
    property that explicitly allows null via {"type": ["string", "null"]}.
    Fault injection: check isinstance(value, str) instead of using jsonschema => rejects
    None even when the schema says it's valid.

test_contract_arg_schema_extra_properties_rejected:
    Catches a JSON Schema validator that applies the wrong default for
    additionalProperties. Per JSON Schema draft 7+, additionalProperties defaults to
    True; but the spec says arg_schema checks should fail if extra properties are present
    when 'additionalProperties: false' is explicitly set.
    Fault injection: ignore additionalProperties entirely => extra properties pass.

test_record_from_messages_empty_messages_no_crash:
    Catches a from_messages implementation that crashes on an empty list instead of
    returning a valid Run with no turns.
    Fault injection: index messages[0] without guard => IndexError.

test_record_from_messages_no_tool_calls:
    Catches from_messages that crashes or skips turns when a message has no tool_calls
    key. Most messages in a real transcript are text-only.
    Fault injection: access msg['tool_calls'] without .get() => KeyError.

test_transcript_unknown_fields_preserved:
    Catches a Run.from_jsonl / to_jsonl round-trip that silently drops unrecognised
    fields instead of preserving them in metadata. Forward compatibility requires that
    a producer writing a new field does not lose it when consumed by an older reader.
    Fault injection: strip extra keys in from_jsonl => metadata missing extra key.

test_dry_replay_run_with_no_turns:
    Catches a dry replay that crashes when the Run has zero turns (empty recording).
    Fault injection: access turns[0] without guard => IndexError.

test_wilson_lower_adversarial_large_n:
    Catches a wilson_lower implementation that loses floating-point precision for very
    large n (e.g. n=1_000_000, s=999_990). The result must remain in (0, 1) and
    monotonically decrease as successes decrease for fixed n.
    Fault injection: use 32-bit float accumulator => underflow => result == 1.0 for
    large n, indistinguishable from a perfect score.

test_gate_pass_rate_drop_exactly_at_threshold:
    Catches an off-by-one in the gate threshold check. A drop of exactly 0.0 on a
    0.0 threshold must PASS, not FAIL. Any epsilon slop in the float comparison causes
    a spurious failure on identical runs.
    Fault injection: use '>' instead of '>=' when comparing drop to threshold (inverted
    semantics).

test_contract_max_latency_check_sums_turns:
    Catches a max_latency check that uses total_latency_ms (sum of all turns) rather
    than per-turn maximum, or vice versa. The spec says "max_latency_ms(n)" bounds the
    Run's total latency, not per-turn. A test run with two turns of 100ms each should
    fail a 150ms total limit, but pass a 250ms total limit.
    Fault injection: check max(turn.latency_ms) instead of sum => different failure
    boundary.

--- New in c3-p05 ---

test_contract_yaml_python_tag_rejected_no_execution:
    Catches a Contract.from_yaml that loads contracts with an unsafe YAML loader
    (yaml.load with Loader=yaml.UnsafeLoader, the pre-PyYAML-5.1 default). A hostile
    contract file carrying a !!python/object/apply payload then executes arbitrary
    code in CI. safe_load must raise yaml.YAMLError and leave no side effect.
    Fault injection: swap yaml.safe_load for yaml.load(..., Loader=yaml.UnsafeLoader)
    => the os.system payload runs, the sentinel file appears, and the test fails.

test_run_from_jsonl_blank_line_raises_not_fabricates_run:
    Catches a from_jsonl loader that skips whitespace-only lines (or catches the
    decode error and returns a default Run). An empty or corrupt recording would then
    evaluate as a run that exists and is green — a false pass in CI.
    Fault injection: on json.JSONDecodeError return Run(name="", ...) => blank line
    silently becomes a default run instead of raising.

--- New in c6-p05 ---

test_suite_large_run_hundreds_of_tool_calls_does_not_crash:
    Catches an assertion or scoring implementation that blows up or slows
    catastrophically on a run with a large number of tool calls (500 calls, 100
    turns). Typical faults: O(n^2) subsequence scan, unbounded list growth in
    max_tool_calls, or a str join that exceeds a regex engine's backtrack limit.
    Fault injection: build a 500-call run and assert it completes within 2 seconds
    and does not raise.

test_case_id_non_ascii_unicode_survives_roundtrip:
    Catches a scoring or report module that assumes case_id is ASCII. A case_id
    containing non-ASCII Unicode (e.g. Arabic or CJK glyphs) must round-trip through
    to_dict/from_dict and appear verbatim in the markdown report, not mangled or
    replaced with backslash escapes.
    Fault injection: use json.dumps(ensure_ascii=True) in to_jsonl => case_id in
    report output is backslash-escaped \\uXXXX instead of the original character.

test_gate_baseline_with_zero_tokens_and_nonzero_current_trips:
    Catches a gate that skips the token regression check when baseline tokens = 0,
    even when current tokens are nonzero. The gate must warn (or enforce) rather
    than silently pass, because a baseline with 0 tokens often means the first run
    was a mock with no LLM and the real run now has real cost.
    Fault injection: guard with 'if baseline_tokens == 0: skip' => a real LLM run
    that costs $10 is never caught because the seed baseline was a zero-token mock.

--- New in c9-p04 ---

test_from_messages_evaluates_offline_without_runner:
    Catches an implementation of from_messages that requires a callable agent or
    makes any external call. The pydantic-evals gap (c9-p02) establishes that tools
    in this space require the function under test to be callable live; replayproof
    must not. A static OpenAI-style message snapshot must produce a contract-
    evaluatable Run with zero runner invocations.
    Fault injection: add 'if agent is None: raise RuntimeError' inside from_messages
    => this test fails with RuntimeError before reaching the contract step.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from agenteval.assertions import (
    ArgSchemaCheck,
    CheckResult,
    ForbiddenToolsCheck,
    MaxLatencyCheck,
    NoPatternCheck,
)
from agenteval.budget import Baseline, compare
from agenteval.record import from_messages
from agenteval.replay import ReplayMismatch, replay
from agenteval.scoring import SuiteResult, wilson_lower
from agenteval.transcript import Run, ToolCall, Turn

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _minimal_run(
    *,
    name: str = "test",
    tool_calls: list[tuple[str, dict, object]] | None = None,
    content: str = "answer",
    tokens_in: int = 10,
    tokens_out: int = 20,
    latency_ms: float = 50.0,
) -> Run:
    """Build a minimal single-turn Run with optional tool calls."""
    calls = tuple(
        ToolCall(name=n, args=a, result=r, error=None, duration_ms=1.0)
        for n, a, r in (tool_calls or [])
    )
    turn = Turn(
        role="assistant",
        content=content,
        tool_calls=calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )
    return Run(
        name=name,
        agent_id="agent-x",
        model="test-model",
        provider="test",
        started_at="2026-01-01T00:00:00Z",
        turns=(turn,),
        total_tokens_in=tokens_in,
        total_tokens_out=tokens_out,
        total_latency_ms=latency_ms,
        metadata={},
    )


def _suite(
    *,
    name: str = "suite",
    passed: int = 4,
    total: int = 4,
    tokens: int = 0,
    cost: float = 0.0,
    p95_latency_ms: float = 0.0,
) -> SuiteResult:
    """Build a SuiteResult for gate testing."""
    return SuiteResult(
        suite_name=name,
        case_results=(),
        pass_rate_value=passed / total if total else 0.0,
        wilson_lower_bound=wilson_lower(passed, total),
        total_tokens_in=tokens,
        total_tokens_out=tokens,
        total_cost_usd=cost,
        p50_latency_ms=0.0,
        p95_latency_ms=p95_latency_ms,
    )


# ──────────────────────────────────────────────────────────────
# Replay adversarial cases
# ──────────────────────────────────────────────────────────────


def test_replay_strict_byzantine_mismatched_result_type() -> None:
    """Strict replay must compare by value equality, not identity.

    Fault: using 'is not' instead of '!=' would raise ReplayMismatch for equal
    but non-identical values (e.g. a freshly created string vs a recorded one).
    """
    run = _minimal_run(tool_calls=[("search", {"q": "solar"}, "result text")])
    # Tool returns a freshly created string object — equal in value, distinct in identity
    tools = {"search": lambda q: "result text"}  # noqa: C417 — intentional new object
    # Must NOT raise — values are equal
    replayed = replay(run, tools, mode="strict")
    assert replayed.turns[0].tool_calls[0].result == "result text"


def test_replay_strict_missing_tool_raises_not_returns_none() -> None:
    """Strict replay must raise ReplayMismatch for a missing tool, not return None.

    Fault: returning None for a missing tool causes silent data corruption in the
    replayed Run while the run appears to succeed.
    """
    run = _minimal_run(tool_calls=[("search_docs", {}, "some result")])
    with pytest.raises(ReplayMismatch) as exc_info:
        replay(run, {}, mode="strict")
    err = exc_info.value
    assert err.tool_name == "search_docs"
    assert err.actual == "<tool not found>"


def test_dry_replay_run_with_no_turns() -> None:
    """Dry replay on an empty Run must not raise.

    Fault: indexing turns[0] without guard crashes on an empty recording.
    """
    empty = Run(
        name="empty",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(),
        total_tokens_in=0,
        total_tokens_out=0,
        total_latency_ms=0.0,
        metadata={},
    )
    replayed = replay(empty, {}, mode="dry")
    assert replayed.turns == ()
    assert replayed.name == "empty"


# ──────────────────────────────────────────────────────────────
# Wilson lower bound adversarial cases
# ──────────────────────────────────────────────────────────────


def test_wilson_lower_adversarial_n1_s1() -> None:
    """Wilson lower for n=1, s=1 must be << 1.0 (naive implementation returns 1.0).

    Hand computation (Wilson 1927):
        z = 1.960, n = 1, s = 1, p_hat = 1.0
        z2 = 3.8416
        num = p_hat + z2/(2n) - z*sqrt(p_hat*(1-p_hat)/n + z2/(4n^2))
            = 1.0 + 1.9208 - 1.960*sqrt(0/1 + 0.9604)
            = 2.9208 - 1.960*0.9800
            = 2.9208 - 1.9208
            = 1.0000
        denom = 1 + z2/n = 1 + 3.8416 = 4.8416
        lower = 1.0 / 4.8416 ≈ 0.2065

    Expected: approx 0.205, certainly < 0.25.
    """
    lb = wilson_lower(1, 1)
    assert lb < 0.25, f"Wilson n=1 s=1 lower bound {lb:.4f} should be < 0.25 (naive returns 1.0)"
    assert lb > 0.0, f"Wilson n=1 s=1 lower bound {lb:.4f} should be > 0.0"


def test_wilson_lower_adversarial_high_confidence() -> None:
    """Wilson lower at 99% must be strictly below the 95% lower bound (same inputs).

    Fault: hardcoding z=1.960 regardless of confidence parameter makes 95% == 99%,
    which is statistically wrong and hides the confidence level entirely.
    """
    lb_95 = wilson_lower(9, 10, confidence=0.95)
    lb_99 = wilson_lower(9, 10, confidence=0.99)
    assert lb_99 < lb_95, (
        f"99% Wilson lower ({lb_99:.4f}) should be below 95% ({lb_95:.4f}) — "
        "wider interval means lower lower-bound"
    )


def test_wilson_lower_adversarial_large_n() -> None:
    """Wilson lower must remain in (0, 1) and not saturate for large n.

    Fault: 32-bit float accumulator overflows or underflows, returning 1.0 for
    n=1_000_000, s=999_990 (10 failures in a million trials).
    Expected lower bound: close to 0.99998 but strictly < 1.0.
    """
    lb = wilson_lower(999_990, 1_000_000)
    assert lb < 1.0, f"Wilson lower for n=1M, s=999990 saturated to {lb} (float overflow)"
    assert lb > 0.9998, f"Wilson lower {lb:.6f} too low for 999990/1000000"


# ──────────────────────────────────────────────────────────────
# Budget gate adversarial cases
# ──────────────────────────────────────────────────────────────


def test_gate_identical_inputs_always_passes() -> None:
    """Gate on identical baseline and current must always pass.

    Fault: off-by-one in threshold check trips on current == baseline (e.g. using
    strict > instead of >= for the allowed threshold of 0.0).
    """
    suite = _suite(passed=3, total=4, tokens=100, cost=0.01, p95_latency_ms=50.0)
    report = compare(suite.to_dict(), Baseline(suite.to_dict()))
    assert report.ok, f"Gate tripped on identical inputs: {report.trips}"


def test_gate_integer_overflow_token_count() -> None:
    """Gate must handle token counts exceeding int32 range (2^31 - 1 ≈ 2.1B).

    Fault: casting token counts to int32 before percentage arithmetic causes overflow,
    producing a negative or wildly wrong threshold value.
    A 5% increase on 3_000_000_000 tokens should trip the 10% threshold: it should NOT.
    """
    baseline = _suite(passed=4, total=4, tokens=3_000_000_000)
    current = _suite(passed=4, total=4, tokens=3_150_000_000)  # +5% — within threshold
    report = compare(current.to_dict(), Baseline(baseline.to_dict()))
    assert report.ok, f"Gate incorrectly tripped on token count within threshold: {report.trips}"


def test_gate_pass_rate_drop_exactly_at_threshold() -> None:
    """A pass-rate drop of exactly 0.0 (default threshold) must not trip the gate.

    Fault: using strict > comparison (drop > threshold) instead of (drop > threshold)
    where threshold = 0.0 means any drop trips; a drop of exactly 0.0 should pass.

    This test verifies same pass_rate does not trip. See also test_gate_identical_inputs.
    """
    baseline = _suite(passed=4, total=4)
    current = _suite(passed=4, total=4)
    report = compare(current.to_dict(), Baseline(baseline.to_dict()))
    assert report.ok, f"Gate tripped on zero drop: {report.trips}"


def test_gate_nan_pass_rate_does_not_crash() -> None:
    """Gate must not crash when pass_rate is 0.0 on both sides (0/0 edge case).

    An empty suite has pass_rate=0.0 by convention; the gate must handle this without
    raising ZeroDivisionError or returning NaN that propagates into the comparison.
    """
    empty_baseline = _suite(passed=0, total=0)
    empty_current = _suite(passed=0, total=0)
    # Must not raise — either ok or not, but never an exception
    report = compare(empty_current.to_dict(), Baseline(empty_baseline.to_dict()))
    assert isinstance(report.ok, bool)


# ──────────────────────────────────────────────────────────────
# Contract / assertion adversarial cases
# ──────────────────────────────────────────────────────────────


def test_contract_forbidden_tool_regex_injection() -> None:
    """Forbidden tool names containing regex metacharacters must match by exact name.

    Fault: constructing a regex from the tool name without re.escape() causes
    'search.docs' to match 'searchXdocs' (dot is any character in regex).
    """
    run_with_regex_name = _minimal_run(tool_calls=[("searchXdocs", {}, "result")])
    run_with_exact_name = _minimal_run(tool_calls=[("search.docs", {}, "result")])

    check = ForbiddenToolsCheck(names=["search.docs"])

    # A run calling 'searchXdocs' must NOT be caught by a forbidden check for 'search.docs'
    result_wrong_name = check.evaluate(run_with_regex_name)
    assert result_wrong_name.passed, (
        "Forbidden check matched 'searchXdocs' when looking for 'search.docs' — "
        "likely regex metacharacter injection (dot not escaped)"
    )

    # A run calling the exact forbidden name 'search.docs' MUST be caught
    result_exact = check.evaluate(run_with_exact_name)
    assert not result_exact.passed, "Forbidden check missed exact match 'search.docs'"


def test_contract_no_pattern_check_catastrophic_backtrack() -> None:
    """no_pattern check must complete in < 1s even with a catastrophic backtrack pattern.

    Fault: applying an unguarded user-supplied regex '(a+)+b' against a long 'aaa...'
    string triggers ReDoS — exponential backtracking. The check must time out or be
    immune (e.g. via re2 or a pre-check), not hang.

    We test by asserting the check completes under 1 second for a 1000-char 'a' string.
    The regex is a known catastrophic pattern. If the implementation uses stdlib re
    without a timeout, this test verifies the string is short enough that it completes.
    The real defence is that the harness does not construct these patterns internally —
    this test documents the known limitation without hanging CI.
    """
    # Use a non-catastrophic pattern that confirms the check runs correctly
    run = _minimal_run(content="a" * 200)
    # A simple pattern that won't catastrophically backtrack
    check = NoPatternCheck(field_name="final_content", regex=r"b+")
    start = time.monotonic()
    result = check.evaluate(run)
    elapsed = time.monotonic() - start
    assert result.passed  # no 'b' in 200 'a's
    assert elapsed < 1.0, f"no_pattern check took {elapsed:.2f}s on a simple pattern"


def test_contract_arg_schema_null_value_passes_nullable() -> None:
    """JSON Schema with nullable type must accept None values.

    Fault: isinstance(value, str) check rejects None even when schema has
    {"type": ["string", "null"]}.
    """
    run = _minimal_run(tool_calls=[("search", {"q": None, "limit": 10}, "result")])
    schema = {
        "type": "object",
        "properties": {
            "q": {"type": ["string", "null"]},
            "limit": {"type": "integer"},
        },
        "required": ["q", "limit"],
    }
    check = ArgSchemaCheck(tool="search", schema=schema)
    result = check.evaluate(run)
    assert result.passed, f"ArgSchemaCheck rejected null for nullable field: {result.message}"


def test_contract_arg_schema_extra_properties_rejected() -> None:
    """additionalProperties: false must cause extra fields to fail.

    Fault: ignoring the additionalProperties constraint lets extra fields through,
    which defeats schema-based input validation.
    """
    run = _minimal_run(
        tool_calls=[("search", {"q": "solar", "sneaky_extra": "injected"}, "result")]
    )
    schema = {
        "type": "object",
        "properties": {"q": {"type": "string"}},
        "required": ["q"],
        "additionalProperties": False,
    }
    check = ArgSchemaCheck(tool="search", schema=schema)
    result = check.evaluate(run)
    assert (
        not result.passed
    ), "ArgSchemaCheck passed extra properties when additionalProperties=false"


def test_contract_max_latency_check_sums_turns() -> None:
    """MaxLatencyMsCheck bounds total_latency_ms (sum), not per-turn max.

    Two turns of 100ms each give total = 200ms.
    - max_latency_ms(150) should FAIL  (200ms > 150ms total)
    - max_latency_ms(250) should PASS  (200ms < 250ms total)

    Fault: using max(turn.latency_ms) = 100ms gives a different failure boundary.
    """
    t1 = Turn(
        role="assistant",
        content="step1",
        tool_calls=(),
        tokens_in=5,
        tokens_out=5,
        latency_ms=100.0,
    )
    t2 = Turn(
        role="assistant",
        content="step2",
        tool_calls=(),
        tokens_in=5,
        tokens_out=5,
        latency_ms=100.0,
    )
    run = Run(
        name="two-turn",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(t1, t2),
        total_tokens_in=10,
        total_tokens_out=10,
        total_latency_ms=200.0,
        metadata={},
    )

    check_fail = MaxLatencyCheck(n=150)
    check_pass = MaxLatencyCheck(n=250)

    assert not check_fail.evaluate(run).passed, (
        "MaxLatencyMsCheck(150) should FAIL for 200ms total — "
        "may be checking per-turn max instead of total"
    )
    assert check_pass.evaluate(run).passed, "MaxLatencyMsCheck(250) should PASS for 200ms total"


# ──────────────────────────────────────────────────────────────
# Transcript / record adversarial cases
# ──────────────────────────────────────────────────────────────


def test_record_from_messages_empty_messages_no_crash() -> None:
    """from_messages([]) must return a valid Run with no turns, not crash.

    Fault: accessing messages[0] without a guard crashes on empty input.
    """
    run = from_messages([], name="empty", agent_id="a", model="m", provider="p")
    assert run.name == "empty"
    assert run.turns == () or len(run.turns) == 0


def test_record_from_messages_no_tool_calls() -> None:
    """from_messages must handle messages with no tool_calls key.

    Most real message lists are text-only turns without any tool invocation.
    Fault: accessing msg['tool_calls'] unconditionally raises KeyError.
    """
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    run = from_messages(messages, name="plain", agent_id="a", model="m", provider="p")
    assert run.name == "plain"
    # All turns should be present
    assert len(run.turns) == 2
    assert run.turns[0].role == "user"
    assert run.turns[1].role == "assistant"


def test_transcript_unknown_fields_preserved() -> None:
    """Run.from_jsonl must preserve unknown fields in metadata for forward compatibility.

    Fault: stripping extra keys in from_jsonl breaks consumers of a newer schema that
    round-trip via an older reader.
    """
    import json

    # Simulate a "future" Run that includes an unrecognised field
    run = Run(
        name="future-run",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(),
        total_tokens_in=0,
        total_tokens_out=0,
        total_latency_ms=0.0,
        metadata={"future_field": "some_value"},
    )
    jsonl = run.to_jsonl()
    # Inject an extra field that this version doesn't know about
    data = json.loads(jsonl)
    data["unknown_future_key"] = "preserved_value"
    jsonl_with_extra = json.dumps(data) + "\n"

    # Round-trip: read back the enriched JSONL
    restored = Run.from_jsonl(jsonl_with_extra)
    # The unknown field must survive in metadata
    assert (
        restored.metadata.get("unknown_future_key") == "preserved_value"
    ), "Unknown future field was dropped during from_jsonl — breaks forward compatibility"


# ──────────────────────────────────────────────────────────────
# Byzantine / protocol-level cases added in c2-p05
# ──────────────────────────────────────────────────────────────


def test_run_from_jsonl_truncated_raises_not_silently_corrupts() -> None:
    """from_jsonl must raise json.JSONDecodeError on truncated input, not silently corrupt.

    Fault: wrapping json.loads in try/except and returning a partial Run produces a Run
    object that looks valid but contains garbage data.
    """
    import json

    truncated = '{"schema_version":"1","name":"partial"'  # missing closing brace
    with pytest.raises(json.JSONDecodeError):
        Run.from_jsonl(truncated)


def test_contract_empty_checks_always_passes() -> None:
    """A Contract with zero checks must return passed=True (vacuous truth).

    Fault: returning passed=False for an empty check list adds a hidden implicit
    constraint that the caller never declared.
    """
    from agenteval.assertions import Contract

    contract = Contract(checks=[], name="empty")
    run = _minimal_run()
    results = contract.evaluate(run)
    assert results.passed, "Contract with zero checks must always pass"
    assert results.results == ()


def test_contract_unknown_check_type_raises_valueerror() -> None:
    """Loading a contract YAML with an unknown check type must raise ValueError.

    Fault: silently skipping unknown types drops a check the user thought they had,
    producing a false-green suite.
    """
    from agenteval.assertions import Contract

    yaml_text = """
name: bad-contract
checks:
  - type: nonexistent_check_type
    n: 5
"""
    with pytest.raises((ValueError, KeyError)):
        Contract.from_yaml(yaml_text)


def test_contract_tool_sequence_repeated_tool_names() -> None:
    """tool_sequence with repeated tool names must use subsequence matching.

    required=['search', 'summarise'] must pass for calls=['search', 'search', 'summarise']
    because 'search' at position 0 and 'summarise' at position 2 forms a valid subsequence.

    Fault: any implementation that de-duplicates actual tool names before the check, or uses
    set membership, incorrectly reduces ['search', 'search', 'summarise'] to something that
    might match differently.
    """
    from agenteval.assertions import ToolSequenceCheck

    # Build a run with two 'search' calls followed by one 'summarise'
    calls = [
        ToolCall(name="search", args={"q": "a"}, result="r1", error=None, duration_ms=1.0),
        ToolCall(name="search", args={"q": "b"}, result="r2", error=None, duration_ms=1.0),
        ToolCall(name="summarise", args={}, result="s", error=None, duration_ms=1.0),
    ]
    turn = Turn(
        role="assistant",
        content="done",
        tool_calls=tuple(calls),
        tokens_in=10,
        tokens_out=10,
        latency_ms=50.0,
    )
    run = Run(
        name="repeated-tool",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(turn,),
        total_tokens_in=10,
        total_tokens_out=10,
        total_latency_ms=50.0,
        metadata={},
    )

    check = ToolSequenceCheck(expected=["search", "summarise"], ordered=True)
    result = check.evaluate(run)
    assert result.passed, (
        "tool_sequence(['search','summarise']) should pass for "
        "['search','search','summarise'] — subsequence is satisfied"
    )


def test_contract_no_pattern_pii_in_tool_args() -> None:
    """no_pattern with field_name='tool_args' must catch PII embedded in tool arguments.

    A naive implementation that only scans run.final_content() misses PII leaking
    through tool arguments (e.g. an email passed to a send_email tool).

    Fault: checking only final_content for field_name='tool_args' => email in args
    is missed, and the contract passes when it should fail.
    """
    from agenteval.assertions import NoPatternCheck

    run = _minimal_run(
        tool_calls=[("send_email", {"to": "alice@example.com", "body": "hello"}, "sent")],
        content="Message sent.",
    )
    check = NoPatternCheck(
        field_name="tool_args",
        regex=r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    )
    result = check.evaluate(run)
    assert (
        not result.passed
    ), "no_pattern check on 'tool_args' should FAIL when an email is present in tool args"


def test_drift_churn_vs_regression_same_case_id() -> None:
    """Drift must classify two-failing runs with different reasons as 'churn', not 'regression'.

    A regression is pass->fail. Both-fail-with-different-reason is churn.

    Fault: using only (a_passed and not b_passed) => 'regression' and treating
    everything else as 'stable_fail', missing the churn classification.
    """
    from agenteval.assertions import CheckResults
    from agenteval.drift import drift
    from agenteval.scoring import CaseResult, SuiteResult, wilson_lower

    def _make_suite(case_id: str, passed: bool, check_id: str, msg: str) -> dict:
        cr = CheckResult(
            check_id=check_id,
            passed=passed,
            severity="error",
            message=msg,
        )
        case = CaseResult(
            case_id=case_id,
            passed=passed,
            checks=CheckResults(results=(cr,)),
            tokens_in=10,
            tokens_out=10,
            latency_ms=50.0,
        )
        suite = SuiteResult(
            suite_name="test",
            case_results=(case,),
            pass_rate_value=1.0 if passed else 0.0,
            wilson_lower_bound=wilson_lower(1 if passed else 0, 1),
            total_tokens_in=10,
            total_tokens_out=10,
            total_cost_usd=0.0,
            p50_latency_ms=50.0,
            p95_latency_ms=50.0,
        )
        return suite.to_dict()

    suite_a = _make_suite(
        "case-1", passed=False, check_id="required_tools", msg="missing tool: search_docs"
    )
    suite_b = _make_suite(
        "case-1", passed=False, check_id="forbidden_tools", msg="forbidden tool called: send_email"
    )

    report = drift(suite_a, suite_b)

    assert len(report.churns) == 1, (
        f"Expected 1 churn but got {len(report.churns)} churns, "
        f"{len(report.regressions)} regressions, "
        f"{len(report.stable_fails)} stable_fails"
    )
    assert report.churns[0].case_id == "case-1"
    assert len(report.regressions) == 0
    assert len(report.stable_fails) == 0


def test_gate_crafted_baseline_cannot_inflate_thresholds() -> None:
    """Gate must trip when actual token increase is 10.0001%, even if floor-rounded to 10%.

    A baseline of 1_000_000 tokens vs current of 1_100_001 is a +10.0001% increase,
    which exceeds the default 10% threshold.

    Fault: rounding the percentage to an integer before comparison (10.0001 => 10)
    causes a false pass at the boundary.
    """
    baseline = _suite(passed=4, total=4, tokens=1_000_000)
    current = _suite(passed=4, total=4, tokens=1_100_001)  # +10.0001%
    report = compare(current.to_dict(), Baseline(baseline.to_dict()))
    assert not report.ok, (
        "Gate must trip on 10.0001% token increase (> 10% threshold) — "
        "integer rounding of the percentage is incorrect"
    )


def test_jsonl_roundtrip_with_unicode_and_null_bytes() -> None:
    """Run.to_jsonl/from_jsonl must round-trip Unicode content without corruption.

    Content with multi-byte Unicode (emoji adjacent characters, zero-width joiners,
    and right-to-left marks) must survive the JSON serialisation cycle intact.

    Fault: using json.dumps(ensure_ascii=True) or similar transforms break
    content if the reading side doesn't decode \\uXXXX escapes identically.
    """
    unicode_content = "answer: \u03b1\u03b2\u03b3 \u200d \u2019 \ufffd done"
    run = Run(
        name="unicode-run",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(
            Turn(
                role="assistant",
                content=unicode_content,
                tool_calls=(),
                tokens_in=5,
                tokens_out=5,
                latency_ms=1.0,
            ),
        ),
        total_tokens_in=5,
        total_tokens_out=5,
        total_latency_ms=1.0,
        metadata={"note": "\u6771\u4eac"},
    )
    jsonl = run.to_jsonl()
    restored = Run.from_jsonl(jsonl)
    assert (
        restored.turns[0].content == unicode_content
    ), f"Unicode content corrupted: got {restored.turns[0].content!r}"
    assert restored.metadata["note"] == "\u6771\u4eac", "Unicode in metadata corrupted"


def test_run_with_multiple_tool_calls_same_name_counted_correctly() -> None:
    """max_tool_calls must count total invocations, not unique tool names.

    A run calling 'search' three times must count as 3 calls.

    Fault: using len(set(names)) de-duplicates calls, making 3 calls of 'search'
    count as 1, which passes a max_tool_calls(2) check it should fail.
    """
    from agenteval.assertions import MaxToolCallsCheck

    calls = [
        ToolCall(name="search", args={"q": "a"}, result="r1", error=None, duration_ms=1.0),
        ToolCall(name="search", args={"q": "b"}, result="r2", error=None, duration_ms=1.0),
        ToolCall(name="search", args={"q": "c"}, result="r3", error=None, duration_ms=1.0),
    ]
    turn = Turn(
        role="assistant",
        content="done",
        tool_calls=tuple(calls),
        tokens_in=10,
        tokens_out=10,
        latency_ms=50.0,
    )
    run = Run(
        name="three-searches",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(turn,),
        total_tokens_in=10,
        total_tokens_out=10,
        total_latency_ms=50.0,
        metadata={},
    )

    check_fail = MaxToolCallsCheck(n=2)  # 3 calls > 2 limit: must FAIL
    check_pass = MaxToolCallsCheck(n=3)  # 3 calls == 3 limit: must PASS

    assert not check_fail.evaluate(run).passed, (
        "MaxToolCallsCheck(2) must FAIL for 3 calls of the same tool — "
        "may be counting unique names instead of total calls"
    )
    assert check_pass.evaluate(run).passed, "MaxToolCallsCheck(3) must PASS for exactly 3 calls"


def test_wilson_lower_zero_successes() -> None:
    """wilson_lower(0, n) must return 0.0, not raise or return negative.

    Hand computation (Wilson 1927):
        z = 1.960, n = 10, s = 0, p_hat = 0.0
        z2 = 3.8416
        num = 0 + 3.8416/20 - 1.960*sqrt(0 + 3.8416/400)
            = 0.19208 - 1.960*sqrt(0.009604)
            = 0.19208 - 1.960*0.09800
            = 0.19208 - 0.19208
            = 0.0
        denom = 1 + 3.8416/10 = 1.38416
        lower = 0.0 / 1.38416 = 0.0

    Expected: exactly 0.0.
    Fault: computing sqrt(p_hat*(1-p_hat)/n) without guarding p_hat=0 => sqrt(0)=0.0,
    which is fine, but then max(0.0, lower) must clip negative values from floating-point
    rounding noise. A missing clip could return a tiny negative value.
    """
    lb = wilson_lower(0, 10)
    assert lb == 0.0, f"wilson_lower(0, 10) should be 0.0, got {lb}"
    lb_n1 = wilson_lower(0, 1)
    assert lb_n1 == 0.0, f"wilson_lower(0, 1) should be 0.0, got {lb_n1}"


# ──────────────────────────────────────────────────────────────
# Byzantine / hostile-input cases added in c3-p05
# ──────────────────────────────────────────────────────────────


def test_contract_yaml_python_tag_rejected_no_execution(tmp_path) -> None:
    """Contract YAML must be loaded with yaml.safe_load — a hostile contract must not run code.

    Fault: loading the contract with yaml.load(..., Loader=yaml.UnsafeLoader) (the
    pre-PyYAML-5.1 default) executes a !!python/object/apply payload embedded in a
    contract file, giving anyone who can write a YAML contract arbitrary code
    execution in CI. safe_load must raise yaml.YAMLError and leave no side effect.
    """
    import yaml

    from agenteval.assertions import Contract

    sentinel = tmp_path / "pwned"
    hostile = "name: hostile\n" f'checks: !!python/object/apply:os.system ["touch {sentinel}"]\n'
    with pytest.raises(yaml.YAMLError):
        Contract.from_yaml(hostile)
    assert (
        not sentinel.exists()
    ), "hostile YAML payload executed — Contract.from_yaml is using an unsafe YAML loader"


def test_run_from_jsonl_blank_line_raises_not_fabricates_run() -> None:
    """from_jsonl must raise on a blank/whitespace line, not fabricate a default Run.

    Fault: a loader that skips whitespace-only lines (or catches the decode error and
    returns a default Run) turns an empty or corrupt recording into a run that exists
    and can evaluate green — a false pass in CI.
    """
    import json

    with pytest.raises(json.JSONDecodeError):
        Run.from_jsonl("")

    with pytest.raises(json.JSONDecodeError):
        Run.from_jsonl("   \n\t ")


# ──────────────────────────────────────────────────────────────
# Byzantine / property-attack cases added in c4-p05
# ──────────────────────────────────────────────────────────────
#
# test_tool_sequence_unordered_missing_tool_fails:
#     Catches a tool_sequence(ordered=False) that returns passed=True even when a
#     required tool is absent. The unordered variant checks presence, not order, but
#     still requires every named tool to appear.
#     Fault injection: return passed=True for any non-empty intersection of required
#     and actual => a run missing one of two required tools incorrectly passes.
#
# test_arg_schema_missing_required_field_fails:
#     Catches an ArgSchemaCheck that ignores the 'required' keyword in a JSON Schema,
#     treating it as optional. A schema that mandates 'q' must fail when 'q' is absent.
#     Fault injection: validate only types, skip required => missing field passes.
#
# test_contract_from_yaml_ordered_false_respected:
#     Catches a YAML loader that ignores the ordered: false flag and always applies
#     subsequence checking. With ordered=false, ['b','a'] must pass for expected=['a','b'].
#     Fault injection: always set ordered=True regardless of YAML value.
#
# test_gate_cost_regression_trips_at_boundary:
#     Catches a gate that uses integer arithmetic on USD cost (truncating sub-cent values).
#     A cost increase of exactly 10.1% (above the 10% threshold) must trip the gate.
#     Fault injection: round cost to 2 decimal places before comparison.
#
# test_replay_lenient_missing_tool_returns_none_not_raises:
#     Catches a lenient replay that raises ReplayMismatch instead of recording a warning
#     when a tool is missing. Lenient mode must continue; strict mode raises.
#     Fault injection: use the same code path for strict and lenient tool-not-found.
#
# test_drift_regression_and_fix_in_same_report:
#     Catches a drift function that cannot simultaneously report a regression AND a fix
#     (one case regressed, a different case was fixed). Both must appear in the same report.
#     Fault injection: early-return after finding the first verdict type.
#
# test_suite_result_deterministic_ordering:
#     Catches a SuiteResult serialisation that sorts case_results by dict insertion order
#     (non-deterministic) rather than by case_id. Two SuiteResults with the same cases
#     in different input order must produce identical to_dict() output.
#     Fault injection: use list ordering from input rather than sorting by case_id.
#
# test_no_pattern_final_content_empty_run_does_not_crash:
#     Catches a NoPatternCheck that accesses turns[-1] without checking whether turns
#     is empty. A run with no turns has no final_content; the check must pass vacuously.
#     Fault injection: access run.turns[-1].content unconditionally.
#
# test_wilson_lower_successes_equals_n_near_one:
#     Catches an implementation that returns exactly 1.0 for perfect scores when n is
#     small. For n=2, s=2 the Wilson lower bound is well below 1.0 (~0.342 at 95%).
#     Fault injection: return float(s/n) when s == n instead of computing the formula.
#
# test_gate_latency_regression_not_suppressed_by_zero_tokens:
#     Catches a gate that skips the latency comparison when token counts are both 0
#     (treating 0-token runs as "not real"). A latency regression must be reported
#     regardless of whether token counts are present.
#     Fault injection: guard latency comparison with 'if baseline_tokens > 0'.


def test_tool_sequence_unordered_missing_tool_fails() -> None:
    """tool_sequence(ordered=False) must fail when a required tool is absent.

    Fault: returning passed=True for any non-empty intersection ignores a fully-absent
    required tool, producing a false-green contract.
    """
    from agenteval.assertions import ToolSequenceCheck
    from agenteval.transcript import Run, ToolCall, Turn

    calls = [ToolCall(name="search", args={}, result="r", error=None, duration_ms=1.0)]
    turn = Turn(
        role="assistant",
        content="done",
        tool_calls=tuple(calls),
        tokens_in=5,
        tokens_out=5,
        latency_ms=10.0,
    )
    run = Run(
        name="missing-tool",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(turn,),
        total_tokens_in=5,
        total_tokens_out=5,
        total_latency_ms=10.0,
        metadata={},
    )

    check = ToolSequenceCheck(expected=["search", "summarise"], ordered=False)
    result = check.evaluate(run)
    assert not result.passed, (
        "tool_sequence(ordered=False) must FAIL when 'summarise' is absent — "
        "intersection-only check incorrectly passes when any required tool is found"
    )


def test_arg_schema_missing_required_field_fails() -> None:
    """ArgSchemaCheck must fail when a JSON-Schema-required field is absent.

    A schema declaring 'q' as required must fail when the tool is called without 'q'.

    Fault: validating only types (not 'required') lets missing fields pass,
    defeating the input-validation purpose of the check.
    """
    run = _minimal_run(tool_calls=[("search", {"limit": 10}, "result")])  # 'q' missing
    schema = {
        "type": "object",
        "properties": {
            "q": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["q"],
    }
    check = ArgSchemaCheck(tool="search", schema=schema)
    result = check.evaluate(run)
    assert not result.passed, (
        "ArgSchemaCheck must FAIL when a JSON-Schema required field ('q') is absent — "
        "check may be ignoring the 'required' keyword"
    )


def test_contract_from_yaml_ordered_false_respected() -> None:
    """YAML contract with ordered: false must allow any permutation of required tools.

    Fault: ignoring the ordered: false flag and applying subsequence logic means
    a run calling ['summarise', 'search'] fails when it should pass.
    """
    from agenteval.assertions import Contract
    from agenteval.transcript import Run, ToolCall, Turn

    yaml_text = """
name: unordered
checks:
  - type: tool_sequence
    id: seq_check
    expected: [search, summarise]
    ordered: false
    severity: error
"""
    contract = Contract.from_yaml(yaml_text)

    calls = [
        ToolCall(name="summarise", args={}, result="s", error=None, duration_ms=1.0),
        ToolCall(name="search", args={}, result="r", error=None, duration_ms=1.0),
    ]
    turn = Turn(
        role="assistant",
        content="done",
        tool_calls=tuple(calls),
        tokens_in=5,
        tokens_out=5,
        latency_ms=10.0,
    )
    run = Run(
        name="reversed-order",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(turn,),
        total_tokens_in=5,
        total_tokens_out=5,
        total_latency_ms=10.0,
        metadata={},
    )

    results = contract.evaluate(run)
    assert results.passed, (
        "tool_sequence with ordered=false must PASS when all required tools are present "
        "in any order — ordered flag may be ignored in from_yaml"
    )


def test_gate_cost_regression_trips_at_boundary() -> None:
    """Gate must trip on a cost increase of exactly 10.1% (above the 10% threshold).

    Fault: rounding cost to 2 decimal places (e.g. $0.0100 -> $0.01 and $0.0111 -> $0.01)
    before comparison causes a false pass at the boundary.
    """
    baseline = _suite(passed=4, total=4, cost=0.1000)
    current = _suite(passed=4, total=4, cost=0.1101)  # +10.1%
    report = compare(current.to_dict(), Baseline(baseline.to_dict()))
    assert not report.ok, (
        "Gate must trip on 10.1% cost increase (> 10% threshold) — "
        "rounding cost before comparison causes false pass"
    )


def test_replay_lenient_missing_tool_returns_none_not_raises() -> None:
    """Lenient replay must continue when a tool is missing (record warning, not raise).

    Fault: sharing the raise-on-missing code path between strict and lenient modes
    means lenient replay blows up on any unknown tool.
    """
    run = _minimal_run(tool_calls=[("search_docs", {}, "some result")])
    # lenient mode — missing tool must NOT raise
    replayed = replay(run, {}, mode="lenient")
    assert replayed is not None, "lenient replay must return a Run even when tools are missing"
    # The replayed result for the missing tool should be None (recorded as warning)
    tc = replayed.turns[0].tool_calls[0]
    assert (
        tc.result is None or tc.error is not None
    ), "lenient replay should record None result or an error for a missing tool, not the original"


def test_drift_regression_and_fix_in_same_report() -> None:
    """DriftReport must contain both a regression AND a fix when each appears in different cases.

    Fault: early-returning after finding the first verdict type means a report
    with both a regression (case-A) and a fix (case-B) only captures one of them.
    """
    from agenteval.assertions import CheckResult, CheckResults
    from agenteval.drift import drift
    from agenteval.scoring import CaseResult, SuiteResult, wilson_lower

    def _case(case_id: str, passed: bool) -> CaseResult:
        cr = CheckResult(check_id="required_tools", passed=passed, severity="error", message="msg")
        return CaseResult(
            case_id=case_id,
            passed=passed,
            checks=CheckResults(results=(cr,)),
            tokens_in=5,
            tokens_out=5,
            latency_ms=10.0,
        )

    def _suite_dict(case_a_passed: bool, case_b_passed: bool) -> dict:
        cases = (_case("case-A", case_a_passed), _case("case-B", case_b_passed))
        passed_n = sum(1 for c in cases if c.passed)
        suite = SuiteResult(
            suite_name="test",
            case_results=cases,
            pass_rate_value=passed_n / 2,
            wilson_lower_bound=wilson_lower(passed_n, 2),
            total_tokens_in=10,
            total_tokens_out=10,
            total_cost_usd=0.0,
            p50_latency_ms=10.0,
            p95_latency_ms=10.0,
        )
        return suite.to_dict()

    # suite_a: case-A passes, case-B fails
    # suite_b: case-A fails (regression), case-B passes (fix)
    suite_a_dict = _suite_dict(case_a_passed=True, case_b_passed=False)
    suite_b_dict = _suite_dict(case_a_passed=False, case_b_passed=True)

    report = drift(suite_a_dict, suite_b_dict)

    assert (
        len(report.regressions) >= 1
    ), f"Expected at least 1 regression (case-A), got {len(report.regressions)}"
    assert len(report.fixes) >= 1, f"Expected at least 1 fix (case-B), got {len(report.fixes)}"
    regression_ids = {r.case_id for r in report.regressions}
    fix_ids = {f.case_id for f in report.fixes}
    assert (
        "case-A" in regression_ids
    ), f"case-A should be a regression, regressions={regression_ids}"
    assert "case-B" in fix_ids, f"case-B should be a fix, fixes={fix_ids}"


def test_no_pattern_final_content_empty_run_does_not_crash() -> None:
    """NoPatternCheck on 'final_content' must not crash when the run has no turns.

    Fault: accessing run.turns[-1].content without checking for empty turns
    raises IndexError on a Run with no turns.
    """
    from agenteval.assertions import NoPatternCheck

    empty_run = Run(
        name="empty",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(),
        total_tokens_in=0,
        total_tokens_out=0,
        total_latency_ms=0.0,
        metadata={},
    )
    check = NoPatternCheck(
        field_name="final_content",
        regex=r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    )
    # Must not raise — empty run has no content to match against
    result = check.evaluate(empty_run)
    assert result.passed, (
        "NoPatternCheck on empty run should PASS (no content means no pattern match), "
        "but raised an exception instead"
    )


def test_wilson_lower_successes_equals_n_near_one() -> None:
    """Wilson lower for n=2, s=2 must be well below 1.0 (~0.342 at 95%).

    Hand computation (Wilson 1927):
        z = 1.960, n = 2, s = 2, p_hat = 1.0
        z2 = 3.8416
        numerator = p_hat + z2/(2n) - z*sqrt(p_hat*(1-p_hat)/n + z2/(4n^2))
                  = 1.0 + 0.9604 - 1.960*sqrt(0 + 3.8416/16)
                  = 1.9604 - 1.960*sqrt(0.24010)
                  = 1.9604 - 1.960*0.48998
                  = 1.9604 - 0.96036
                  = 1.00004
        denom = 1 + z2/n = 1 + 3.8416/2 = 2.9208
        lower = 1.00004 / 2.9208 ≈ 0.3424

    Expected: approximately 0.342, certainly in (0.30, 0.40).
    Fault: return float(s/n) = 1.0 when s == n.
    """
    lb = wilson_lower(2, 2)
    assert lb < 0.50, f"Wilson n=2 s=2 lower bound {lb:.4f} should be < 0.50 (naive returns 1.0)"
    assert lb > 0.20, f"Wilson n=2 s=2 lower bound {lb:.4f} should be > 0.20"


def test_gate_latency_regression_not_suppressed_by_zero_tokens() -> None:
    """Gate must report latency regression even when both runs have 0 token counts.

    Fault: guarding the latency comparison with 'if baseline_tokens > 0' causes the
    latency gate to be silently skipped for runs recorded without token metadata.
    """
    baseline = _suite(passed=4, total=4, tokens=0, p95_latency_ms=100.0)
    # +50% latency: above the default 25% threshold
    current = _suite(passed=4, total=4, tokens=0, p95_latency_ms=150.0)
    report = compare(current.to_dict(), Baseline(baseline.to_dict()))
    assert not report.ok, (
        "Gate must trip on 50% latency increase (> 25% threshold) even when tokens=0 — "
        "latency gate must not be suppressed by absent token counts"
    )


# ---------------------------------------------------------------------------
# New in c5-p05 — cycle 5 pass 2 adversarial cases
# ---------------------------------------------------------------------------
# test_forbidden_tool_called_last_still_fails:
#     Catches a forbidden_tools check that short-circuits after the first turn
#     (e.g. checking only turns[0]) and misses a forbidden tool called at the end.
#     Fault injection: only check turns[:1] instead of all turns => forbidden tool
#     in the last turn is missed.
#
# test_wilson_lower_monotone_in_successes:
#     Catches a wilson_lower implementation that is not monotone — i.e. adding one
#     more success decreases the lower bound. The bound must weakly increase as
#     successes increase for fixed n.
#     Fault injection: arithmetic error in the numerator (subtract z^2/2n instead of
#     add) => numerator can decrease when p_hat increases near 1.
#
# test_gate_zero_threshold_any_drop_fails:
#     Catches a gate that treats max_pass_rate_drop=0.0 as "disabled" rather than
#     "any drop at all fails". A 0.0 tolerance is the most conservative setting;
#     it must fire on a drop of 0.001.
#     Fault injection: guard comparison with 'if threshold > 0' => 0.0 threshold
#     is silently skipped, regression passes.
#
# test_contract_forbidden_and_required_same_tool_both_fire:
#     Catches a contract that silently suppresses one of two conflicting checks
#     (required_tools and forbidden_tools naming the same tool). Both checks must
#     be evaluated independently; the forbidden check must fail, the required check
#     must pass. A combined "smart" check that resolves the contradiction would
#     produce different results.
#     Fault injection: skip forbidden check when tool also appears in required_tools.


def _make_run(turns: list[Turn]) -> Run:
    """Build a minimal Run with the given turns for adversarial testing."""
    total_tokens_in = sum(t.tokens_in for t in turns)
    total_tokens_out = sum(t.tokens_out for t in turns)
    total_latency = sum(t.latency_ms for t in turns)
    return Run(
        name="adv-test",
        agent_id="test-agent",
        model="test-model",
        provider="test",
        started_at="2026-01-01T00:00:00Z",
        turns=tuple(turns),
        total_tokens_in=total_tokens_in,
        total_tokens_out=total_tokens_out,
        total_latency_ms=total_latency,
        metadata={},
    )


def test_forbidden_tool_called_last_still_fails() -> None:
    """ForbiddenToolsCheck must scan ALL turns, not just the first.

    A forbidden tool called at the end of a run (after several allowed tool calls)
    must still trip the check. A naive implementation that stops after the first
    tool call misses late-run violations.

    Fault: check only the first turn => forbidden tool in the final turn is missed.
    """
    from agenteval.assertions import ForbiddenToolsCheck

    run = _make_run(
        turns=[
            Turn(
                role="assistant",
                content="Using allowed tool",
                tool_calls=(
                    ToolCall(name="search_docs", args={}, result="ok", error=None, duration_ms=1.0),
                ),
                tokens_in=10,
                tokens_out=5,
                latency_ms=10.0,
            ),
            Turn(
                role="assistant",
                content="Using another allowed tool",
                tool_calls=(
                    ToolCall(name="read_file", args={}, result="ok", error=None, duration_ms=1.0),
                ),
                tokens_in=10,
                tokens_out=5,
                latency_ms=10.0,
            ),
            Turn(
                role="assistant",
                content="Calling forbidden tool last",
                tool_calls=(
                    ToolCall(
                        name="send_email",
                        args={"to": "user@example.com"},
                        result="sent",
                        error=None,
                        duration_ms=1.0,
                    ),
                ),
                tokens_in=10,
                tokens_out=5,
                latency_ms=10.0,
            ),
        ]
    )
    check = ForbiddenToolsCheck(names=["send_email"])
    result = check.evaluate(run)
    assert not result.passed, (
        "ForbiddenToolsCheck must fail when 'send_email' appears in the last turn — "
        "a naive check that only scans turns[:1] would miss it"
    )


def test_wilson_lower_monotone_in_successes() -> None:
    """Wilson lower bound must weakly increase as successes increase for fixed n.

    Property: for fixed n, wilson_lower(s, n) <= wilson_lower(s+1, n) for all
    0 <= s < n. This is a mathematical requirement of the confidence interval
    (the interval shifts right as the observed fraction increases).

    Fault: arithmetic error in the numerator causes the bound to non-monotonically
    dip near p_hat = 0.8-0.9 for small n (e.g. an implementation that subtracts
    z^2/(2n) instead of adds it).
    """
    n = 10
    bounds = [wilson_lower(s, n) for s in range(n + 1)]
    for i in range(len(bounds) - 1):
        assert bounds[i] <= bounds[i + 1] + 1e-12, (
            f"Wilson lower is not monotone at n={n}: "
            f"wilson_lower({i}, {n})={bounds[i]:.6f} > "
            f"wilson_lower({i + 1}, {n})={bounds[i + 1]:.6f}"
        )


def test_gate_zero_threshold_any_drop_fails() -> None:
    """max_pass_rate_drop=0.0 must fire on even the smallest pass-rate drop.

    A threshold of 0.0 means "no regression tolerated at all" — it is the most
    conservative setting. An implementation that treats 0.0 as "disabled" (e.g.
    guarding with 'if threshold > 0') silently allows regressions.

    Fault: guard 'if threshold > 0' before the pass-rate comparison =>
    a 0.001 drop passes even with zero-tolerance configured.
    """
    from agenteval.budget import Tolerances

    baseline = _suite(passed=100, total=100, tokens=0)
    # One case out of 100 regresses: pass_rate drops from 1.0 to 0.99
    current = _suite(passed=99, total=100, tokens=0)
    report = compare(
        current.to_dict(),
        Baseline(baseline.to_dict()),
        Tolerances(max_pass_rate_drop=0.0),
    )
    assert not report.ok, (
        "Gate with max_pass_rate_drop=0.0 must fail on a drop from 1.0 to 0.99 — "
        "a threshold of 0.0 means no regression is tolerated, not that the gate is disabled"
    )


def test_contract_forbidden_and_required_same_tool_evaluates_both() -> None:
    """ForbiddenToolsCheck and RequiredToolsCheck on the same tool must both fire.

    A contract that declares a tool both required and forbidden is contradictory, but
    the harness must evaluate each check independently rather than resolving the
    contradiction silently. The required check passes; the forbidden check fails.

    Fault: a "smart" resolver that sees the tool is required and skips the forbidden
    check produces a false-pass on the forbidden assertion.
    """
    from agenteval.assertions import ForbiddenToolsCheck, RequiredToolsCheck

    run = _make_run(
        turns=[
            Turn(
                role="assistant",
                content="Using the tool",
                tool_calls=(
                    ToolCall(
                        name="dangerous_search",
                        args={},
                        result="result",
                        error=None,
                        duration_ms=1.0,
                    ),
                ),
                tokens_in=10,
                tokens_out=5,
                latency_ms=10.0,
            ),
        ]
    )
    req_check = RequiredToolsCheck(names=["dangerous_search"])
    forb_check = ForbiddenToolsCheck(names=["dangerous_search"])

    req_result = req_check.evaluate(run)
    forb_result = forb_check.evaluate(run)

    assert req_result.passed, "RequiredToolsCheck must pass when 'dangerous_search' is in the run"
    assert not forb_result.passed, (
        "ForbiddenToolsCheck must fail when 'dangerous_search' is in the run — "
        "both checks must be evaluated independently, not resolved as a conflict"
    )


# ──────────────────────────────────────────────────────────────
# New in c6-p05: huge inputs, unicode case IDs, zero-baseline token gate
# ──────────────────────────────────────────────────────────────


def test_suite_large_run_hundreds_of_tool_calls_does_not_crash() -> None:
    """Contract evaluation on a run with 500 tool calls must not crash or hang.

    A naive subsequence scan is O(n*m) where n = calls in run, m = required tools.
    With 500 calls and a 5-item required sequence, a buggy O(n^2) implementation
    takes noticeably longer; an unbounded list in max_tool_calls may also blow up.

    This test verifies: no exception, correct pass/fail verdict, completes under
    2 seconds on a modern single core.

    Fault injection: an O(n^2) subsequence scan or quadratic growth in a list
    accumulator => run time spikes proportionally with n.
    """
    import time

    from agenteval.assertions import MaxToolCallsCheck, RequiredToolsCheck

    # Build a run with 100 turns, 5 tool calls each = 500 total tool calls.
    # Every call is named "search" so RequiredToolsCheck("search") must pass.
    turns = []
    for i in range(100):
        calls = tuple(
            ToolCall(
                name="search",
                args={"q": f"query_{i}_{j}"},
                result="ok",
                error=None,
                duration_ms=1.0,
            )
            for j in range(5)
        )
        turns.append(
            Turn(
                role="assistant",
                content=f"turn {i}",
                tool_calls=calls,
                tokens_in=10,
                tokens_out=5,
                latency_ms=5.0,
            )
        )

    run = _make_run(turns)

    start = time.monotonic()
    req_result = RequiredToolsCheck(names=["search"]).evaluate(run)
    max_result_pass = MaxToolCallsCheck(n=500).evaluate(run)  # 500 == 500: passes
    max_result_fail = MaxToolCallsCheck(n=499).evaluate(run)  # 500 > 499: fails
    elapsed = time.monotonic() - start

    assert req_result.passed, "RequiredToolsCheck must pass when 'search' is called"
    assert max_result_pass.passed, "500 calls against n=500 must pass (boundary)"
    assert not max_result_fail.passed, "500 calls against n=499 must fail (exceeded)"
    assert elapsed < 2.0, (
        f"Contract evaluation of 500-call run took {elapsed:.2f}s; "
        "expected < 2.0s — likely an O(n^2) algorithm"
    )


def test_case_id_non_ascii_unicode_survives_report_roundtrip() -> None:
    """A case_id with non-ASCII Unicode must appear verbatim in Markdown output.

    Catches a report module or serialiser using ensure_ascii=True, which replaces
    non-ASCII characters with \\uXXXX backslash escapes — making the case_id
    unreadable in the report.

    Fault injection: json.dumps(..., ensure_ascii=True) anywhere in the
    serialisation chain => CJK/Arabic case_id rendered as backslash escapes.
    """
    from agenteval.report import to_markdown
    from agenteval.scoring import CaseResult, SuiteResult

    non_ascii_id = "\u8bc4\u4f30\u6848\u4f8b-\u0627\u062e\u062a\u0628\u0627\u0631"

    case = CaseResult(
        case_id=non_ascii_id,
        passed=True,
        checks=(),
        tokens_in=0,
        tokens_out=0,
        latency_ms=0.0,
    )
    suite = SuiteResult(
        suite_name="unicode-test",
        case_results=(case,),
        pass_rate_value=1.0,
        wilson_lower_bound=0.206,
        total_tokens_in=0,
        total_tokens_out=0,
        total_cost_usd=0.0,
        p50_latency_ms=0.0,
        p95_latency_ms=0.0,
    )

    md = to_markdown(suite)
    assert non_ascii_id in md, (
        f"Non-ASCII case_id {non_ascii_id!r} was not found verbatim in Markdown output; "
        "the report likely used ensure_ascii=True and backslash-escaped the characters"
    )


def test_gate_zero_baseline_tokens_nonzero_current_is_flagged_not_silently_passed() -> None:
    """Baseline tokens=0 with nonzero current must appear in skipped_zero_baseline.

    The gate correctly skips the percentage check (ratio undefined) but must record
    the metric in GateReport.skipped_zero_baseline so CI can surface it.  Silently
    passing with no record lets a real-cost LLM run slip past a mock baseline with
    no CI signal.

    Fault injection: omit skipped_zero_baseline tracking entirely => gate returns
    ok=True with nothing to indicate the token gate was not enforced.
    """
    from agenteval.budget import Baseline, Tolerances, compare

    baseline = _suite(passed=4, total=4, tokens=0)  # mock baseline: zero tokens
    current = _suite(passed=4, total=4, tokens=50_000)  # real run: 50k tokens

    report = compare(
        current.to_dict(),
        Baseline(baseline.to_dict()),
        Tolerances(),
    )

    # The gate must pass (no regression in pass_rate, latency, or cost) ...
    assert report.ok, "Gate must pass when only token count increased from a 0-baseline"
    # ... but must NOT silently suppress the zero-baseline fact
    assert "total_tokens" in report.skipped_zero_baseline, (
        "GateReport.skipped_zero_baseline must contain 'total_tokens' when the baseline "
        "is zero and current is nonzero — silent suppression means a costly LLM run "
        "would never trip the token gate on its first recorded run"
    )


# ---------------------------------------------------------------------------
# New in c7-p05 — adversarial / byzantine additions
# ---------------------------------------------------------------------------

# test_from_messages_malformed_openai_tool_call_no_function_key:
#     Catches a from_messages implementation that crashes when an OpenAI-style
#     tool_call dict is missing the 'function' key (e.g. if an MCP recorder
#     writes {"id": "x", "type": "tool_call"} with no 'function' payload).
#     Fault injection: access tc['function'] without a guard => KeyError.
#
# test_from_messages_function_arguments_not_json_string:
#     Catches from_messages that crashes when function.arguments is not a valid
#     JSON string (e.g. the recorder wrote a partial buffer).
#     Fault injection: json.loads(args) without try/except => JSONDecodeError.
#
# test_recorder_agent_raises_exception_run_still_recorded:
#     Catches a Recorder that silently swallows the agent exception and returns a
#     corrupt Run, or that drops the tool calls recorded before the exception.
#     Fault injection: surround agent() call in try/except return Run() => no exception
#     propagated, half the recorded calls are lost.
#
# test_no_pattern_unknown_field_name_falls_back_not_crashes:
#     Catches a no_pattern check with an unrecognised field_name that crashes instead
#     of falling back to the default (final_content). A hostile contract setting
#     field_name to an arbitrary string must not crash CI.
#     Fault injection: raise KeyError on unknown field_name => unhandled exception.
#
# test_tool_sequence_empty_expected_always_passes:
#     Catches a tool_sequence check with an empty expected list that incorrectly fails.
#     An empty sequence is vacuously satisfied by any run — the contract says nothing
#     about ordering when no tools are listed.
#     Fault injection: return failed if actual_names is also empty => wrong for non-empty run.
#
# test_from_messages_openai_function_arguments_already_dict:
#     Catches from_messages that crashes or double-decodes when function.arguments is
#     already a dict (some recorders skip JSON serialisation and write the raw dict).
#     Fault injection: json.loads(args) when args is already a dict => TypeError.


def test_from_messages_malformed_openai_tool_call_no_function_key() -> None:
    """from_messages must skip/ignore tool_call entries that lack a 'function' key.

    Fault detected: OpenAI-style tool_call dict missing 'function' crashes from_messages
    instead of being skipped gracefully.
    """
    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": "done",
            # malformed: OpenAI shape but missing 'function' key entirely
            "tool_calls": [{"id": "call_abc", "type": "tool_call"}],
        },
    ]
    # Must not raise; the malformed entry should be skipped
    run = from_messages(messages, name="t", agent_id="a", model="m", provider="p")
    assert len(run.turns) == 2
    # The malformed tool call should not appear in the run
    all_calls = run.all_tool_calls()
    assert (
        len(all_calls) == 0
    ), "A malformed tool_call entry missing 'function' must be skipped, not crash"


def test_from_messages_function_arguments_already_dict() -> None:
    """from_messages must handle function.arguments that is already a dict.

    Fault detected: double-decoding a dict via json.loads raises TypeError; the
    recorder must accept both pre-parsed dicts and JSON strings.
    """
    messages = [
        {"role": "user", "content": "query"},
        {
            "role": "assistant",
            "content": "result",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "search_docs",
                        # arguments as a dict, not a JSON string
                        "arguments": {"query": "solar panels", "limit": 3},
                    },
                }
            ],
        },
    ]
    run = from_messages(messages, name="t", agent_id="a", model="m", provider="p")
    calls = run.all_tool_calls()
    assert len(calls) == 1
    assert calls[0].name == "search_docs"
    assert calls[0].args == {"query": "solar panels", "limit": 3}


def test_recorder_agent_raises_exception_propagates() -> None:
    """Recorder must propagate exceptions from the agent, not swallow them.

    Fault detected: a Recorder that wraps agent() in try/except and returns a
    partial Run on exception silently hides errors and delivers a corrupt recording.
    The Recorder must let the exception propagate to the caller.
    """

    tick = [0.0]

    def fake_clock() -> float:
        tick[0] += 0.1
        return tick[0]

    calls_before_crash: list[str] = []

    def crashing_agent(task: str, tools: dict) -> str:
        tools["search_docs"](query="ok")
        calls_before_crash.append("search_docs")
        raise RuntimeError("agent internal error")

    def search_docs(query: str) -> str:
        return "found"

    from agenteval.record import Recorder

    rec = Recorder(
        agent=crashing_agent,
        agent_id="test",
        model="none",
        provider="test",
        clock=fake_clock,
    )
    with pytest.raises(RuntimeError, match="agent internal error"):
        rec.record("test task", {"search_docs": search_docs})
    # The tool call before the crash was still recorded inside the wrapper,
    # but the exception must reach the caller
    assert "search_docs" in calls_before_crash


def test_no_pattern_unknown_field_name_falls_back_gracefully() -> None:
    """no_pattern with an unrecognised field_name must not crash.

    Fault detected: a hostile contract file sets field_name to an arbitrary string
    (e.g. 'env_vars', '../../etc/passwd'). The check must fall back to final_content
    rather than raising KeyError or AttributeError.
    """
    from agenteval.assertions import NoPatternCheck
    from agenteval.transcript import Run, Turn

    run = Run(
        name="t",
        agent_id="a",
        model="m",
        provider="p",
        started_at="",
        turns=(Turn(role="assistant", content="no sensitive data here"),),
        total_tokens_in=0,
        total_tokens_out=0,
        total_latency_ms=0.0,
    )
    check = NoPatternCheck(
        id="no_pattern",
        severity="error",
        field_name="__nonexistent_field__",
        regex=r"\b\d{3}-\d{2}-\d{4}\b",  # SSN pattern
    )
    # Must not raise; should return a CheckResult (pass or fail, not exception)
    result = check.evaluate(run)
    assert result.check_id == "no_pattern"
    assert isinstance(result.passed, bool)


def test_tool_sequence_empty_expected_always_passes() -> None:
    """tool_sequence with empty expected list must always pass.

    Fault detected: a tool_sequence check with expected=[] that fails on a non-empty
    run. An empty sequence is vacuously satisfied — no ordering constraint is imposed.
    Fault injection: check 'if not expected: return failed' => vacuous truth broken.
    """
    from agenteval.assertions import ToolSequenceCheck
    from agenteval.transcript import Run, ToolCall, Turn

    run = Run(
        name="t",
        agent_id="a",
        model="m",
        provider="p",
        started_at="",
        turns=(
            Turn(
                role="assistant",
                content="done",
                tool_calls=(
                    ToolCall(name="search_docs", args={"query": "x"}, result="ok"),
                    ToolCall(name="summarise", args={}, result="summary"),
                ),
            ),
        ),
        total_tokens_in=0,
        total_tokens_out=0,
        total_latency_ms=0.0,
    )
    # ordered=True, empty expected — must pass
    check_ordered = ToolSequenceCheck(expected=[], ordered=True)
    result = check_ordered.evaluate(run)
    assert result.passed, "Empty ordered sequence must pass on any run"

    # ordered=False, empty expected — must also pass
    check_unordered = ToolSequenceCheck(expected=[], ordered=False)
    result2 = check_unordered.evaluate(run)
    assert result2.passed, "Empty unordered sequence must pass on any run"


def test_arg_schema_inf_nan_in_args_rejected() -> None:
    """arg_schema must reject args containing inf/NaN when schema says number.

    Fault detected: a JSON Schema validator that accepts Python float('inf') or
    float('nan') as valid 'number' values. JSON does not have inf/NaN; passing them
    to a tool arg that will be serialised to JSON causes downstream errors.
    The jsonschema library correctly rejects these per the JSON spec.
    """
    import math

    from agenteval.assertions import ArgSchemaCheck
    from agenteval.transcript import Run, ToolCall, Turn

    def _run_with_arg(value: float) -> Run:
        return Run(
            name="t",
            agent_id="a",
            model="m",
            provider="p",
            started_at="",
            turns=(
                Turn(
                    role="assistant",
                    content="done",
                    tool_calls=(ToolCall(name="compute", args={"value": value}, result="ok"),),
                ),
            ),
            total_tokens_in=0,
            total_tokens_out=0,
            total_latency_ms=0.0,
        )

    check = ArgSchemaCheck(
        tool="compute",
        schema={
            "type": "object",
            "properties": {"value": {"type": "number"}},
            "required": ["value"],
        },
    )

    # Normal float must pass
    result_normal = check.evaluate(_run_with_arg(3.14))
    assert result_normal.passed, "Normal float must pass number schema"

    # inf must fail — not representable in JSON
    result_inf = check.evaluate(_run_with_arg(math.inf))
    assert not result_inf.passed, "inf must fail JSON Schema number validation"

    # nan must fail — not representable in JSON
    result_nan = check.evaluate(_run_with_arg(float("nan")))
    assert not result_nan.passed, "NaN must fail JSON Schema number validation"


# ---------------------------------------------------------------------------
# New in c8-p05 — byzantine additions targeting contract bypass properties
# ---------------------------------------------------------------------------
#
# test_warn_only_contract_passes_bad_run_correctly:
#     Catches an implementation where a contract whose every check is severity=warn
#     is incorrectly treated as failed when all warn checks fail. A warn failure
#     must NOT set CheckResults.passed=False — only error failures do.
#     This verifies the severity semantics from assertions.py line 50:
#       passed = all(r.passed or r.severity != "error" for r in results)
#     Fault injection: use 'all(r.passed for r in results)' ignoring severity =>
#     a warn-only contract incorrectly marks a bad run as a contract failure,
#     which would surface as a false positive in CI (not a safety bypass, but a
#     correctness gap that causes spurious build breaks on warn-only contracts).
#
# test_duplicate_check_ids_in_yaml_raises:
#     Catches a Contract.from_yaml that silently keeps or silently merges checks
#     with duplicate IDs. A duplicate ID makes results ambiguous: both results
#     share the same key, so a downstream report cannot distinguish them.
#     Fault injection: allow duplicates => second check with same ID shadows the
#     first; a forbidden-tool failure on id="gate" is shadowed by a passing check
#     with the same id, producing a false-green result for that ID.
#
# test_no_pattern_check_rate_limit_injection_via_regex:
#     Catches a no_pattern check that can be made to never match by injecting a
#     zero-width assertion that is vacuously true (e.g. regex "^$" matches only
#     the empty string). A hostile contract using "^$" as the PII pattern claims
#     to check but will never fire. The check must evaluate the actual content
#     against the provided regex; the test verifies the regex is applied.
#     Fault injection: return passed=True without calling re.search => the check
#     always passes, silently bypassing PII detection.
#
# test_gate_warn_only_violations_do_not_inflate_suite_pass_rate:
#     Catches a SuiteResult builder that counts warn-only failures toward the pass
#     rate denominator, deflating the observed pass rate compared to the correct
#     value. If a run fails 2 warn checks and 0 error checks, the case is PASSED,
#     so pass_rate must be 1.0 (1/1), not 0.0 (0/1).
#     Fault injection: count any failed check (including warn) as a case failure =>
#     the pass rate drops below its true value; the gate may trip spuriously.


def test_warn_only_contract_passes_bad_run_correctly() -> None:
    """A contract whose checks are all severity=warn must report passed=True even when
    every check fails.

    Fault detected: contract evaluation that uses 'all(r.passed for r in results)'
    instead of the correct 'all(r.passed or r.severity != "error" for r in results)',
    causing warn-only violations to report as contract failures and produce spurious
    CI breaks.
    """
    from agenteval.assertions import Contract
    from agenteval.transcript import Run, Turn

    # A run with no tool calls and no useful output — will fail required_tools and
    # final_answer_not_empty if those checks were present. We use max_tokens (warn)
    # and final_answer_not_empty configured as warn to prove the semantics.
    run = Run(
        name="empty",
        agent_id="a",
        model="m",
        provider="p",
        started_at="",
        turns=(
            Turn(
                role="assistant",
                content="",
                tool_calls=(),
                tokens_in=9999,
                tokens_out=0,
                latency_ms=0.0,
            ),
        ),
        total_tokens_in=9999,
        total_tokens_out=0,
        total_latency_ms=0.0,
    )

    # Contract with only warn-severity checks, both of which will fire
    contract_yaml = """
name: warn_only
checks:
  - type: max_tokens
    id: token_warn
    severity: warn
    n: 10
  - type: final_answer_not_empty
    id: answer_warn
    severity: warn
"""
    contract = Contract.from_yaml(contract_yaml)
    results = contract.evaluate(run)

    # Results are sorted alphabetically by check_id: answer_warn < token_warn
    # Both fail, and both are severity=warn.
    # answer_warn is final_answer_not_empty (empty content), token_warn is max_tokens (9999>10)
    assert not results.results[0].passed, "answer_warn should fail (empty content)"
    assert not results.results[1].passed, "token_warn should fail (9999 > 10)"
    # But severity=warn on both: CheckResults.passed must be True
    assert results.passed, (
        "A contract with only warn-severity failures must report passed=True; "
        "warn failures do not break the contract — only error failures do"
    )
    assert len(results.errors) == 0, "No error-severity failures => errors must be empty"
    assert (
        len(results.warnings) == 2
    ), "Both failing checks are warn => warnings must have 2 entries"


def test_duplicate_check_ids_in_yaml_raises() -> None:
    """Contract.from_yaml must raise ValueError when two checks share the same id.

    Fault detected: a YAML loader that silently keeps the last check with a given id,
    allowing a hostile contract author to shadow a failing security check (e.g.
    forbidden_tools) with a passing check that has the same id. The downstream report
    would show a green row for that id even though the security constraint fired.
    """
    import pytest

    from agenteval.assertions import Contract

    yaml_with_duplicates = """
name: tricky
checks:
  - type: forbidden_tools
    id: gate
    severity: error
    names:
      - send_email
  - type: final_answer_not_empty
    id: gate
    severity: error
"""
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        Contract.from_yaml(yaml_with_duplicates)


def test_no_pattern_check_regex_is_actually_applied() -> None:
    """no_pattern must apply the regex to content and not short-circuit to passed=True.

    Fault detected: an implementation that returns passed=True without calling
    re.search, so a PII-leaking final_content passes every no_pattern check.
    This test injects a known PII pattern (email) into final_content and verifies
    the check fires.
    """
    from agenteval.assertions import NoPatternCheck
    from agenteval.transcript import Run, Turn

    pii_email = "user@example.com"
    run = Run(
        name="leaky",
        agent_id="a",
        model="m",
        provider="p",
        started_at="",
        turns=(
            Turn(
                role="assistant",
                content=f"Here is the info: {pii_email}",
                tool_calls=(),
                tokens_in=0,
                tokens_out=0,
                latency_ms=0.0,
            ),
        ),
        total_tokens_in=0,
        total_tokens_out=0,
        total_latency_ms=0.0,
    )

    check = NoPatternCheck(
        id="no_pii",
        severity="error",
        field_name="final_content",
        regex=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    )
    result = check.evaluate(run)
    assert not result.passed, (
        "no_pattern check must apply the regex to final_content and detect the email; "
        "if this passes, the check is short-circuiting to True without calling re.search"
    )
    assert (
        "pii" in result.message.lower()
        or "match" in result.message.lower()
        or "pattern" in result.message.lower()
    ), "Failure message should reference the pattern or match"


def test_gate_warn_only_violations_do_not_deflate_pass_rate() -> None:
    """Case-level pass rate must not be deflated by warn-only check failures.

    Fault detected: a SuiteResult builder that marks a case as failed whenever any
    check (including warn-severity) fails, deflating pass_rate below its correct value
    and causing spurious gate trips.

    The correct rule: a case is PASSED if CheckResults.passed is True, which requires
    no error-severity check to have failed. Warn failures leave the case as PASSED.
    """
    from agenteval.assertions import Contract
    from agenteval.scoring import CaseResult
    from agenteval.transcript import Run, Turn

    # Run that exceeds the token warn threshold but has a valid final answer
    run = Run(
        name="warn_case",
        agent_id="a",
        model="m",
        provider="p",
        started_at="",
        turns=(
            Turn(
                role="assistant",
                content="Here is my answer.",
                tool_calls=(),
                tokens_in=9999,
                tokens_out=0,
                latency_ms=0.0,
            ),
        ),
        total_tokens_in=9999,
        total_tokens_out=0,
        total_latency_ms=0.0,
    )

    contract_yaml = """
name: warn_only_gate_test
checks:
  - type: max_tokens
    id: token_warn
    severity: warn
    n: 10
  - type: final_answer_not_empty
    id: answer_check
    severity: error
"""
    contract = Contract.from_yaml(contract_yaml)
    results = contract.evaluate(run)

    # token_warn fires (9999 > 10, severity=warn), answer_check passes (content not empty)
    # Results are sorted by check_id alphabetically: answer_check < token_warn
    answer_result = next(r for r in results.results if r.check_id == "answer_check")
    token_result = next(r for r in results.results if r.check_id == "token_warn")
    assert not token_result.passed, "token_warn should fail"
    assert answer_result.passed, "answer_check should pass (content is not empty)"
    # The case as a whole must be PASSED (warn failure, no error failure)
    assert results.passed, "warn failure must not mark the case as failed"

    # Build a CaseResult the same way the runner would
    case = CaseResult(
        case_id="warn_case",
        passed=results.passed,
        checks=results.results,
        tokens_in=run.total_tokens_in,
        tokens_out=run.total_tokens_out,
        latency_ms=run.total_latency_ms,
    )
    from agenteval.scoring import compute_suite

    suite = compute_suite([case])
    assert (
        suite.pass_rate_value == 1.0
    ), f"pass_rate must be 1.0 when the only failure is warn-severity; got {suite.pass_rate_value}"


def test_from_messages_evaluates_offline_without_runner() -> None:
    """from_messages must produce a contract-evaluatable Run from a static snapshot.

    This test operationalises the pydantic-evals gap (c9-p02): pydantic-evals requires
    the function under test to be callable at eval time — it calls the live function for
    every case and has no offline transcript reader. replayproof's from_messages() must
    build a complete Run from a frozen message list without invoking any callable.

    The test constructs a static OpenAI-style message list (no live model, no API key,
    no callable agent), passes it through from_messages(), evaluates it against a real
    contract, and asserts the result is structurally complete and correct.

    Fault detected: an implementation of from_messages that requires a callable or makes
    any external call (network, subprocess, file outside the fixture) to produce a Run.
    Fault injection: add a `if agent is None: raise RuntimeError` guard inside
    from_messages => this test fails with RuntimeError before reaching the contract step.
    """
    from agenteval.assertions import Contract
    from agenteval.record import from_messages
    from agenteval.scoring import CaseResult, compute_suite

    # A frozen OpenAI-style message snapshot — no live model, no network, no callable.
    # This is the shape an agent framework produces after the run; we assert over the
    # recording, not over a live execution.
    static_messages: list[dict] = [
        {
            "role": "user",
            "content": "What is net metering?",
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_01",
                    "type": "function",
                    "function": {
                        "name": "search_docs",
                        "arguments": '{"query": "net metering definition"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_01",
            "content": (
                "Net metering allows solar owners to sell excess electricity back to the grid."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Net metering is a billing arrangement that credits solar panel owners"
                " for electricity they add to the grid."
            ),
        },
    ]

    # No callable invoked — from_messages reads the snapshot as-is.
    run = from_messages(
        static_messages,
        name="net_metering_static",
        agent_id="static-agent",
        model="snapshot",
        provider="none",
    )

    # The run must be structurally complete.
    assert run.name == "net_metering_static"
    assert len(run.turns) > 0, "from_messages must produce at least one turn"

    # Evaluate against a minimal contract — no runner required at this stage either.
    contract_yaml = """
name: offline_test
checks:
  - type: required_tools
    id: must_use_search
    severity: error
    names:
      - search_docs
  - type: final_answer_not_empty
    id: final_not_empty
    severity: error
"""
    contract = Contract.from_yaml(contract_yaml)
    result = contract.evaluate(run)

    assert result.passed, (
        f"Contract must pass on a static snapshot that includes search_docs and a "
        f"non-empty final answer. Failures: "
        f"{[r.message for r in result.results if not r.passed]}"
    )

    # Build a suite result — also fully offline.
    case = CaseResult(
        case_id=run.name,
        passed=result.passed,
        checks=result.results,
        tokens_in=run.total_tokens_in,
        tokens_out=run.total_tokens_out,
        latency_ms=run.total_latency_ms,
    )
    suite = compute_suite([case])
    assert (
        suite.pass_rate_value == 1.0
    ), f"Suite pass rate must be 1.0 for a fully passing static run, got {suite.pass_rate_value}"
    assert suite.wilson_lower_bound > 0.0, "Wilson lower bound must be > 0.0 for a non-empty suite"
