"""Model-swap drift detection between two SuiteResult snapshots.

Drift analysis compares two suite runs (e.g. model A vs model B, or
baseline vs current) and classifies per-case verdict changes:

    regression  — was passing, now failing
    fix         — was failing, now passing
    churn       — both failing, different failure reason
    stable_pass — passing in both
    stable_fail — failing in both with same reason

The DriftReport also includes aggregate token and latency deltas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CaseDrift:
    """Drift classification for a single test case.

    Fields:
        case_id: Case identifier.
        verdict: One of 'regression', 'fix', 'churn', 'stable_pass', 'stable_fail'.
        a_passed: Whether case passed in run A.
        b_passed: Whether case passed in run B.
        a_reason: Failure reason in A (empty string if passed).
        b_reason: Failure reason in B (empty string if passed).
        token_delta: Change in total tokens (B - A).
        latency_delta_ms: Change in latency (B - A).
    """

    case_id: str
    verdict: str
    a_passed: bool
    b_passed: bool
    a_reason: str = ""
    b_reason: str = ""
    token_delta: int = 0
    latency_delta_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "case_id": self.case_id,
            "verdict": self.verdict,
            "a_passed": self.a_passed,
            "b_passed": self.b_passed,
            "a_reason": self.a_reason,
            "b_reason": self.b_reason,
            "token_delta": self.token_delta,
            "latency_delta_ms": self.latency_delta_ms,
        }


@dataclass(frozen=True)
class DriftReport:
    """Aggregate drift summary between two suite runs.

    Fields:
        regressions: Cases that passed in A but fail in B.
        fixes: Cases that failed in A but pass in B.
        churns: Cases that fail in both with different reasons.
        stable_passes: Cases passing in both.
        stable_fails: Cases failing in both with identical reason.
        most_diverged: Top-N cases sorted by abs(token_delta), descending.
        token_delta_total: Total token change across all cases (B - A).
        latency_delta_ms_total: Total latency change (B - A).
    """

    regressions: tuple[CaseDrift, ...]
    fixes: tuple[CaseDrift, ...]
    churns: tuple[CaseDrift, ...]
    stable_passes: tuple[CaseDrift, ...]
    stable_fails: tuple[CaseDrift, ...]
    most_diverged: tuple[CaseDrift, ...]
    token_delta_total: int
    latency_delta_ms_total: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "regressions": [c.to_dict() for c in self.regressions],
            "fixes": [c.to_dict() for c in self.fixes],
            "churns": [c.to_dict() for c in self.churns],
            "stable_passes": [c.to_dict() for c in self.stable_passes],
            "stable_fails": [c.to_dict() for c in self.stable_fails],
            "most_diverged": [c.to_dict() for c in self.most_diverged],
            "token_delta_total": self.token_delta_total,
            "latency_delta_ms_total": self.latency_delta_ms_total,
        }


def drift(a: dict[str, Any], b: dict[str, Any], top_n: int = 5) -> DriftReport:
    """Compute per-case drift between two SuiteResult dicts.

    Args:
        a: Dict from ``SuiteResult.to_dict()`` for run A.
        b: Dict from ``SuiteResult.to_dict()`` for run B.
        top_n: How many most-diverged cases to include.

    Returns:
        DriftReport with classified verdicts and aggregate stats.
    """
    a_cases = {c["case_id"]: c for c in a.get("cases", [])}
    b_cases = {c["case_id"]: c for c in b.get("cases", [])}

    all_ids = sorted(set(a_cases) | set(b_cases))

    regressions: list[CaseDrift] = []
    fixes: list[CaseDrift] = []
    churns: list[CaseDrift] = []
    stable_passes: list[CaseDrift] = []
    stable_fails: list[CaseDrift] = []

    all_cases: list[CaseDrift] = []

    for cid in all_ids:
        a_c = a_cases.get(cid, {})
        b_c = b_cases.get(cid, {})

        a_passed = bool(a_c.get("passed", False))
        b_passed = bool(b_c.get("passed", False))

        a_tok = int(a_c.get("tokens_in", 0)) + int(a_c.get("tokens_out", 0))
        b_tok = int(b_c.get("tokens_in", 0)) + int(b_c.get("tokens_out", 0))
        a_lat = float(a_c.get("latency_ms", 0.0))
        b_lat = float(b_c.get("latency_ms", 0.0))

        # Extract first failing check message as the "reason".
        a_reason = _first_failure_reason(a_c)
        b_reason = _first_failure_reason(b_c)

        tok_delta = b_tok - a_tok
        lat_delta = b_lat - a_lat

        if a_passed and not b_passed:
            verdict = "regression"
        elif not a_passed and b_passed:
            verdict = "fix"
        elif not a_passed and not b_passed and a_reason != b_reason:
            verdict = "churn"
        elif a_passed and b_passed:
            verdict = "stable_pass"
        else:
            verdict = "stable_fail"

        cd = CaseDrift(
            case_id=cid,
            verdict=verdict,
            a_passed=a_passed,
            b_passed=b_passed,
            a_reason=a_reason,
            b_reason=b_reason,
            token_delta=tok_delta,
            latency_delta_ms=lat_delta,
        )
        all_cases.append(cd)

        if verdict == "regression":
            regressions.append(cd)
        elif verdict == "fix":
            fixes.append(cd)
        elif verdict == "churn":
            churns.append(cd)
        elif verdict == "stable_pass":
            stable_passes.append(cd)
        else:
            stable_fails.append(cd)

    most_diverged = sorted(all_cases, key=lambda c: abs(c.token_delta), reverse=True)[:top_n]

    token_delta_total = sum(c.token_delta for c in all_cases)
    latency_delta_total = sum(c.latency_delta_ms for c in all_cases)

    return DriftReport(
        regressions=tuple(regressions),
        fixes=tuple(fixes),
        churns=tuple(churns),
        stable_passes=tuple(stable_passes),
        stable_fails=tuple(stable_fails),
        most_diverged=tuple(most_diverged),
        token_delta_total=token_delta_total,
        latency_delta_ms_total=latency_delta_total,
    )


def _first_failure_reason(case_dict: dict[str, Any]) -> str:
    """Extract the first failing check message from a case dict, or empty string."""
    # When cases are stored from CaseResult.to_dict(), the checks are not
    # serialised at case level (they're on Run level).  We use the case
    # passed flag combined with any message stored in metadata.
    if case_dict.get("passed", True):
        return ""
    return case_dict.get("failure_reason", "")
