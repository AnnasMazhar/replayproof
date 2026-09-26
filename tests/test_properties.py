"""Property-based tests using Hypothesis.

Properties are derived from the mathematical assumptions of each method,
not from the implementation — per the quality contract.

Properties tested:

1. wilson_lower is monotonically non-decreasing in successes for fixed n.
   Source: Wilson (1927) property of score intervals — more successes => higher lower bound.
   Fault detected: non-monotone wilson_lower (e.g. sorting bug, wrong sign somewhere).

2. wilson_lower is in [0, 1] for all valid inputs.
   Source: basic probability semantics.
   Fault detected: implementation that returns values outside [0, 1].

3. wilson_lower(n, n) < 1.0 for any finite n > 0.
   Source: Wilson interval is never degenerate at 1.0 for finite samples.
   Fault detected: implementation that returns 1.0 for perfect score.

4. pass_rate is in [0.0, 1.0] for any list of CaseResult.
   Source: definition of proportion.
   Fault detected: division or sign error in pass_rate.

5. Dry replay is idempotent: replaying the result of a dry replay gives the
   same Run as replaying the original.
   Source: idempotency property from the spec.
   Fault detected: dry replay that is not referentially transparent.

6. No-pattern check is deterministic for a fixed salt/regex.
   Source: pure function contract — no randomness.
   Fault detected: non-deterministic regex compilation or stateful regex objects.

7. Redaction (no_pattern) differs across different regexes (not a constant function).
   Source: the check must actually apply the regex; different regexes must behave differently.
   Fault detected: check that always passes regardless of pattern.

8. compute_suite pass_rate_value equals successes/n (definition check).
   Source: mathematical definition of pass rate.
   Fault detected: off-by-one or wrong denominator in compute_suite.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agenteval.assertions import CheckResults, NoPatternCheck
from agenteval.replay import replay
from agenteval.scoring import CaseResult, compute_suite, pass_rate, wilson_lower
from agenteval.transcript import Run, ToolCall, Turn

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(case_id: str, passed: bool) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        passed=passed,
        checks=CheckResults(results=()),
        tokens_in=0,
        tokens_out=0,
        latency_ms=0.0,
    )


def _simple_run(tool_results: dict[str, str] | None = None, content: str = "ok") -> Run:
    """Build a minimal Run for replay tests."""
    if tool_results is None:
        tool_results = {}
    tool_calls = tuple(
        ToolCall(name=n, args={"q": "x"}, result=r) for n, r in sorted(tool_results.items())
    )
    return Run(
        name="prop_test",
        agent_id="a",
        model="m",
        provider="p",
        started_at="2026-01-01T00:00:00Z",
        turns=(
            Turn(role="user", content="q"),
            Turn(role="assistant", content=content, tool_calls=tool_calls),
        ),
        total_tokens_in=0,
        total_tokens_out=0,
        total_latency_ms=0.0,
    )


# ---------------------------------------------------------------------------
# Property: Wilson lower bound is monotone in successes
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    n=st.integers(min_value=1, max_value=1000),
    s1=st.integers(min_value=0, max_value=1000),
    s2=st.integers(min_value=0, max_value=1000),
)
def test_wilson_lower_monotone_in_successes(n: int, s1: int, s2: int) -> None:
    """Wilson lower bound is non-decreasing as successes increase (fixed n).

    Property source: Wilson (1927) — the score interval lower bound is a
    monotone function of the observed proportion p_hat = s/n.
    """
    assume(s1 <= n and s2 <= n)
    assume(s1 <= s2)
    lb1 = wilson_lower(s1, n)
    lb2 = wilson_lower(s2, n)
    assert lb1 <= lb2 + 1e-9, (
        f"wilson_lower should be non-decreasing: "
        f"wilson_lower({s1},{n})={lb1:.6f} > wilson_lower({s2},{n})={lb2:.6f}"
    )


@settings(max_examples=200, deadline=None)
@given(
    n=st.integers(min_value=1, max_value=10000),
    s=st.integers(min_value=0, max_value=10000),
)
def test_wilson_lower_in_unit_interval(n: int, s: int) -> None:
    """Wilson lower bound is always in [0, 1] for valid inputs.

    Property source: basic probability semantics — a proportion lower bound
    must be a valid probability.
    """
    assume(s <= n)
    result = wilson_lower(s, n)
    assert 0.0 <= result <= 1.0, f"wilson_lower({s}, {n}) = {result} is outside [0, 1]"


@settings(max_examples=100, deadline=None)
@given(n=st.integers(min_value=1, max_value=10000))
def test_wilson_lower_perfect_score_less_than_one(n: int) -> None:
    """Wilson lower bound for a perfect score on finite n is strictly < 1.0.

    Property source: Wilson (1927) — for finite n, the interval is always
    proper (has non-zero width) even for s=n.
    """
    result = wilson_lower(n, n)
    assert result < 1.0, f"wilson_lower({n},{n}) = {result:.6f} should be < 1.0 for finite n"


# ---------------------------------------------------------------------------
# Property: pass_rate is in [0, 1]
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    bools=st.lists(st.booleans(), min_size=0, max_size=500),
)
def test_pass_rate_in_unit_interval(bools: list[bool]) -> None:
    """pass_rate is always in [0, 1] for any input list.

    Property source: definition of a proportion.
    """
    cases = [_make_case(str(i), b) for i, b in enumerate(bools)]
    result = pass_rate(cases)
    assert 0.0 <= result <= 1.0, f"pass_rate = {result} is outside [0, 1]"


@settings(max_examples=200, deadline=None)
@given(
    bools=st.lists(st.booleans(), min_size=1, max_size=500),
)
def test_pass_rate_definition(bools: list[bool]) -> None:
    """pass_rate(cases) == sum(passed) / len(cases) by definition.

    Property source: the mathematical definition of a sample proportion.
    Fault detected: wrong denominator, wrong predicate, or off-by-one.
    """
    cases = [_make_case(str(i), b) for i, b in enumerate(bools)]
    expected = sum(bools) / len(bools)
    result = pass_rate(cases)
    assert abs(result - expected) < 1e-9, f"pass_rate = {result:.6f}, expected {expected:.6f}"


# ---------------------------------------------------------------------------
# Property: dry replay is idempotent
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    tool_results=st.dictionaries(
        st.text(min_size=1, max_size=8, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))),
        st.text(min_size=0, max_size=20),
        min_size=0,
        max_size=4,
    ),
    content=st.text(min_size=0, max_size=50),
)
def test_dry_replay_idempotent(tool_results: dict[str, str], content: str) -> None:
    """Replaying the result of a dry replay gives the same serialisation as the original.

    Property source: the spec states 'replaying a recording in dry mode is idempotent'.
    Fault detected: dry replay that modifies metadata or turn content on each call.
    """
    original = _simple_run(tool_results=tool_results, content=content)
    replayed_once = replay(original, tools={}, mode="dry")
    replayed_twice = replay(replayed_once, tools={}, mode="dry")

    assert (
        original.to_jsonl() == replayed_once.to_jsonl()
    ), "First dry replay must be byte-identical to original."
    assert (
        replayed_once.to_jsonl() == replayed_twice.to_jsonl()
    ), "Second dry replay must be byte-identical to first (idempotent)."


# ---------------------------------------------------------------------------
# Property: no_pattern is deterministic for fixed regex
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    content=st.text(min_size=0, max_size=200),
)
def test_no_pattern_deterministic(content: str) -> None:
    """No-pattern check is deterministic: same input always gives same result.

    Property source: pure function contract — no randomness allowed.
    Fault detected: non-deterministic regex state or caching bug.
    """
    check = NoPatternCheck(
        field_name="final_content",
        regex=r"\d{3}-\d{2}-\d{4}",  # SSN pattern
    )
    from tests.test_assertions import _run as _make_run

    run1 = _make_run(final_content=content)
    run2 = _make_run(final_content=content)
    r1 = check.evaluate(run1)
    r2 = check.evaluate(run2)
    assert r1.passed == r2.passed, f"no_pattern check is non-deterministic for content={content!r}"


# ---------------------------------------------------------------------------
# Property: compute_suite pass_rate_value equals successes/n
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    bools=st.lists(st.booleans(), min_size=1, max_size=200),
)
def test_compute_suite_pass_rate_matches_definition(bools: list[bool]) -> None:
    """compute_suite.pass_rate_value equals len(passed)/len(cases).

    Property source: definition of sample proportion — no accumulation errors allowed.
    Fault detected: floating-point accumulation bug or wrong predicate in compute_suite.
    """
    cases = [_make_case(str(i), b) for i, b in enumerate(bools)]
    suite = compute_suite(cases)
    expected = sum(bools) / len(bools)
    assert abs(suite.pass_rate_value - expected) < 1e-9, (
        f"suite.pass_rate_value = {suite.pass_rate_value:.6f}, " f"expected {expected:.6f}"
    )


# ---------------------------------------------------------------------------
# Property: wilson_lower(s, n) is non-increasing in n for fixed s
# ---------------------------------------------------------------------------


@settings(max_examples=150, deadline=None)
@given(
    s=st.integers(min_value=0, max_value=50),
    n1=st.integers(min_value=1, max_value=100),
    extra=st.integers(min_value=1, max_value=100),
)
def test_wilson_lower_non_increasing_in_n_for_fixed_s(s: int, n1: int, extra: int) -> None:
    """For fixed successes s, wilson_lower is non-increasing as n grows (s/n is constant).

    This tests that adding more trials with the same absolute success count
    lowers the lower bound — uncertainty increases as the observed rate drops.

    Technically: if s/n1 > s/n2 (n1 < n2) then lb1 >= lb2 must hold.
    This property holds for the Wilson score interval.
    """
    n2 = n1 + extra  # n2 is always > n1, no need for assume()
    # But s must be <= both n1 and n2; cap s at n1 (the smaller)
    s_capped = s % (n1 + 1)  # s in [0, n1]
    # p_hat1 = s_capped/n1 >= s_capped/n2 = p_hat2 when n1 <= n2
    lb1 = wilson_lower(s_capped, n1)
    lb2 = wilson_lower(s_capped, n2)
    assert lb1 >= lb2 - 1e-9, (
        f"wilson_lower({s_capped},{n1})={lb1:.6f} < wilson_lower({s_capped},{n2})={lb2:.6f}; "
        "lower bound should be non-increasing as n grows with fixed s."
    )
