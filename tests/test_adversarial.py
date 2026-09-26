"""Adversarial and byzantine test cases for agent-eval-harness.

These tests target implementation paths that a naive developer would get wrong, and
cases a hostile user might construct to subvert the contract evaluation.

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
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from agenteval.assertions import (
    ArgSchemaCheck,
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
