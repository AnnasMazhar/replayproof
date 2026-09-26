"""Tests for budget gate and drift detection.

Faults detected by each test:

TestBudgetGate:
- test_gate_passes_identical_inputs: catches a gate that always trips.
- test_gate_trips_on_pass_rate_drop: catches a gate that ignores pass_rate changes.
- test_gate_trips_on_token_increase: catches a gate that ignores token increases.
- test_gate_ok_on_tokens_within_tolerance: catches a gate that trips on any increase.
- test_gate_report_ok_false_on_trip: catches a gate that returns ok=True on a trip.
- test_gate_trip_names_metric: catches a gate that raises but doesn't name the metric.
- test_gate_no_trip_if_tokens_equal: catches off-by-one in percent comparison.

TestDrift:
- test_drift_detects_regression: catches drift() that misclassifies regression as churn.
- test_drift_classifies_fix: catches drift() that misclassifies fix as regression.
- test_drift_stable_pass: catches drift() that marks stable-pass as something else.
- test_drift_token_delta_total: catches drift() that does not aggregate token deltas.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agenteval.budget import Baseline, Tolerances, compare
from agenteval.drift import drift


def _suite_dict(
    pass_rate: float = 1.0,
    tokens_in: int = 100,
    tokens_out: int = 50,
    p95_latency: float = 200.0,
    cost: float = 0.0,
    cases: list | None = None,
) -> dict:
    """Build a minimal SuiteResult dict for gate/drift testing."""
    if cases is None:
        cases = []
    return {
        "suite_name": "test",
        "pass_rate": pass_rate,
        "wilson_lower": pass_rate * 0.9,
        "total_tokens_in": tokens_in,
        "total_tokens_out": tokens_out,
        "total_cost_usd": cost,
        "p50_latency_ms": p95_latency * 0.5,
        "p95_latency_ms": p95_latency,
        "n_cases": len(cases),
        "n_passed": sum(1 for c in cases if c.get("passed", False)),
        "cases": cases,
        "metadata": {},
    }


def _case(  # noqa: E501 — signature intentionally wide for readability
    case_id: str,
    passed: bool,
    tokens: int = 10,
    latency: float = 50.0,
    reason: str = "",
) -> dict:
    d = {
        "case_id": case_id,
        "passed": passed,
        "tokens_in": tokens,
        "tokens_out": 5,
        "latency_ms": latency,
    }
    if reason:
        d["failure_reason"] = reason
    return d


class TestBudgetGate:
    def test_gate_passes_identical_inputs(self) -> None:
        """Fault: gate always trips even on identical inputs."""
        suite = _suite_dict(pass_rate=0.9, tokens_in=100, tokens_out=50)
        baseline = Baseline(suite)
        report = compare(suite, baseline)
        assert report.ok, f"Gate should pass on identical inputs; trips: {report.trips}"

    def test_gate_trips_on_pass_rate_drop(self) -> None:
        """Fault: gate ignores pass_rate changes."""
        baseline_dict = _suite_dict(pass_rate=0.9)
        current_dict = _suite_dict(pass_rate=0.7)
        baseline = Baseline(baseline_dict)
        report = compare(current_dict, baseline, Tolerances(max_pass_rate_drop=0.0))
        assert not report.ok, "Gate must trip on pass_rate drop from 0.9 to 0.7"
        trip_metrics = [t.metric for t in report.trips]
        assert "pass_rate" in trip_metrics, f"Expected 'pass_rate' trip, got {trip_metrics}"

    def test_gate_trips_on_token_increase(self) -> None:
        """Fault: gate ignores token increases."""
        baseline_dict = _suite_dict(tokens_in=100, tokens_out=0)
        # Increase tokens by 50% > default 10% threshold.
        current_dict = _suite_dict(tokens_in=150, tokens_out=0)
        baseline = Baseline(baseline_dict)
        report = compare(current_dict, baseline, Tolerances(max_token_increase_pct=0.10))
        assert not report.ok, "Gate must trip on 50% token increase (threshold 10%)"
        trip_metrics = [t.metric for t in report.trips]
        assert "total_tokens" in trip_metrics, f"Expected 'total_tokens' trip, got {trip_metrics}"

    def test_gate_ok_on_tokens_within_tolerance(self) -> None:
        """Fault: gate trips on any increase, ignoring tolerance."""
        baseline_dict = _suite_dict(tokens_in=100, tokens_out=0)
        current_dict = _suite_dict(tokens_in=105, tokens_out=0)  # 5% increase < 10% threshold
        baseline = Baseline(baseline_dict)
        report = compare(current_dict, baseline, Tolerances(max_token_increase_pct=0.10))
        assert report.ok, f"5% token increase should be within 10% tolerance; trips: {report.trips}"

    def test_gate_report_ok_false_on_trip(self) -> None:
        """Fault: gate returns ok=True even when a trip occurred."""
        baseline_dict = _suite_dict(pass_rate=1.0)
        current_dict = _suite_dict(pass_rate=0.5)
        baseline = Baseline(baseline_dict)
        report = compare(current_dict, baseline)
        assert report.ok is False, "GateReport.ok must be False when gate trips"

    def test_gate_trip_detail_has_values(self) -> None:
        """Fault: trip detail carries None/empty for baseline_value or current_value."""
        baseline_dict = _suite_dict(pass_rate=0.9)
        current_dict = _suite_dict(pass_rate=0.5)
        baseline = Baseline(baseline_dict)
        report = compare(current_dict, baseline)
        trip = report.trips[0]
        assert trip.baseline_value == pytest.approx(0.9)
        assert trip.current_value == pytest.approx(0.5)

    def test_gate_no_trip_if_tokens_equal(self) -> None:
        """Fault: off-by-one in percent comparison trips on equal token counts."""
        suite = _suite_dict(tokens_in=200, tokens_out=100)
        baseline = Baseline(suite)
        report = compare(suite, baseline)
        assert report.ok, "Identical token counts must not trip the token gate"


class TestDrift:
    def test_drift_detects_regression(self) -> None:
        """Fault: drift() misclassifies regression as stable or churn.

        A case that passed in A and fails in B is a regression.
        """
        case_a = _case("case1", passed=True)
        case_b = _case("case1", passed=False, reason="required_tools: missing search")
        a = _suite_dict(cases=[case_a])
        b = _suite_dict(cases=[case_b])
        report = drift(a, b)
        assert len(report.regressions) == 1, (
            f"Expected 1 regression, got {len(report.regressions)}. "
            f"Fixes: {len(report.fixes)}, Churns: {len(report.churns)}"
        )
        assert report.regressions[0].case_id == "case1"
        assert report.regressions[0].verdict == "regression"

    def test_drift_classifies_fix(self) -> None:
        """Fault: drift() misclassifies fix as regression or stable_fail."""
        case_a = _case("case1", passed=False, reason="some error")
        case_b = _case("case1", passed=True)
        a = _suite_dict(cases=[case_a])
        b = _suite_dict(cases=[case_b])
        report = drift(a, b)
        assert len(report.fixes) == 1, f"Expected 1 fix, got {len(report.fixes)}"
        assert report.fixes[0].verdict == "fix"

    def test_drift_stable_pass(self) -> None:
        """Fault: drift() marks stable-pass cases as something else."""
        case_a = _case("case1", passed=True)
        case_b = _case("case1", passed=True)
        a = _suite_dict(cases=[case_a])
        b = _suite_dict(cases=[case_b])
        report = drift(a, b)
        assert len(report.stable_passes) == 1
        assert len(report.regressions) == 0
        assert report.stable_passes[0].verdict == "stable_pass"

    def test_drift_token_delta_total(self) -> None:
        """Fault: drift() does not sum token deltas across cases."""
        case_a = _case("c1", passed=True, tokens=100)
        case_b = _case("c1", passed=True, tokens=150)
        a = _suite_dict(cases=[case_a])
        b = _suite_dict(cases=[case_b])
        report = drift(a, b)
        # B has 150+5=155 tokens, A has 100+5=105 tokens => delta = +50
        assert (
            report.token_delta_total == 50
        ), f"Expected token_delta_total=50, got {report.token_delta_total}"

    def test_drift_regression_not_fix(self) -> None:
        """Fault: regression classified as fix (inverted pass/fail logic)."""
        case_a = _case("bad_case", passed=True)
        case_b = _case("bad_case", passed=False)
        a = _suite_dict(cases=[case_a])
        b = _suite_dict(cases=[case_b])
        report = drift(a, b)
        assert len(report.fixes) == 0, "Must not classify a regression as a fix"

    def test_drift_churn_both_fail_different_reason(self) -> None:
        """Fault: drift() does not distinguish churn from stable_fail."""
        case_a = _case("c1", passed=False, reason="error_A")
        case_b = _case("c1", passed=False, reason="error_B")
        a = _suite_dict(cases=[case_a])
        b = _suite_dict(cases=[case_b])
        report = drift(a, b)
        assert len(report.churns) == 1, (
            f"Expected 1 churn, got {len(report.churns)}. "
            f"Stable fails: {len(report.stable_fails)}"
        )

    def test_drift_most_diverged_sorted_by_token_delta(self) -> None:
        """Fault: most_diverged list is not sorted by token_delta magnitude."""
        cases_a = [_case(f"c{i}", passed=True, tokens=10) for i in range(5)]
        # Give c3 the largest token increase.
        cases_b = [
            _case("c0", passed=True, tokens=11),
            _case("c1", passed=True, tokens=12),
            _case("c2", passed=True, tokens=13),
            _case("c3", passed=True, tokens=100),  # big delta
            _case("c4", passed=True, tokens=14),
        ]
        a = _suite_dict(cases=cases_a)
        b = _suite_dict(cases=cases_b)
        report = drift(a, b, top_n=3)
        assert (
            report.most_diverged[0].case_id == "c3"
        ), f"Most diverged should be c3, got {report.most_diverged[0].case_id}"


class TestTranscriptRoundTrip:
    """Run serialisation round-trip test."""

    def test_run_jsonl_round_trip(self) -> None:
        """Fault: from_jsonl loses fields or changes types.

        Specifically tests that metadata, schema_version, and all turn fields
        survive a round-trip.
        """
        from agenteval.transcript import Run, ToolCall, Turn

        original = Run(
            name="rt_test",
            agent_id="agent1",
            model="gpt-4",
            provider="openai",
            started_at="2026-01-01T12:00:00Z",
            turns=(
                Turn(role="user", content="hello"),
                Turn(
                    role="assistant",
                    content="world",
                    tool_calls=(ToolCall(name="search", args={"q": "test"}, result="found"),),
                    tokens_in=10,
                    tokens_out=5,
                    latency_ms=150.0,
                ),
            ),
            total_tokens_in=10,
            total_tokens_out=5,
            total_latency_ms=150.0,
            metadata={"extra_key": "extra_value"},
            schema_version="1",
        )

        line = original.to_jsonl()
        restored = Run.from_jsonl(line)

        assert restored.name == original.name
        assert restored.agent_id == original.agent_id
        assert restored.model == original.model
        assert restored.schema_version == original.schema_version
        assert restored.metadata.get("extra_key") == "extra_value"
        assert len(restored.turns) == 2
        assert restored.turns[1].tool_calls[0].name == "search"
        assert restored.turns[1].tool_calls[0].result == "found"

    def test_forward_compatible_unknown_fields(self) -> None:
        """Fault: from_dict crashes on unknown fields instead of preserving them.

        A future schema version may add fields; current code must preserve them
        in metadata rather than raising KeyError.
        """
        from agenteval.transcript import Run

        d = {
            "schema_version": "99",
            "name": "future_run",
            "agent_id": "x",
            "model": "y",
            "provider": "z",
            "started_at": "2099-01-01T00:00:00Z",
            "turns": [],
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_latency_ms": 0.0,
            "future_unknown_field": "should_be_preserved",
        }
        run = Run.from_dict(d)
        assert run.metadata.get("future_unknown_field") == "should_be_preserved"
