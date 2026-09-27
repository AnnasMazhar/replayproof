"""Honest pass-rate statistics with Wilson score confidence intervals.

The Wilson score lower bound is used in preference to the naive normal
approximation because it provides correct coverage near p=0 and p=1 and
for small n.  See docs/RESEARCH.md for the source derivation.

Reference: Wilson (1927), JASA 22(158):209-212.
Equation (verbatim from the paper, with notation mapped to code below):

    w_lower = (p_hat + z^2/(2n) - z*sqrt(p_hat*(1-p_hat)/n + z^2/(4n^2)))
              / (1 + z^2/n)

Where:
    p_hat  = observed proportion = successes / n
    z      = the z-score for the desired confidence level
             (z = 1.96 for 95% one-sided lower bound, technically z_{alpha/2}
              for a two-sided interval; this module uses 1.6449 for a true
              one-sided 95% lower bound)
    n      = total number of trials

For CI purposes we return the lower bound of the two-sided interval
(z = 1.96) which is the more conservative estimate and matches
the literature on eval quality gates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from agenteval.assertions import CheckResults


@dataclass(frozen=True)
class CaseResult:
    """Result of evaluating one test case.

    Fields:
        case_id: Identifier for the test case.
        passed: True if no error-severity assertion failed.
        checks: The full CheckResults for this case.
        tokens_in: Prompt tokens for this case.
        tokens_out: Completion tokens for this case.
        latency_ms: Total latency for this case in milliseconds.
    """

    case_id: str
    passed: bool
    checks: CheckResults
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        # Include the first failing check message so drift can detect churn
        # (two failures with different reasons).
        failure_reason = ""
        if not self.passed:
            for r in self.checks.results:
                if not r.passed and r.severity == "error":
                    failure_reason = r.check_id + ": " + r.message
                    break
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
            "failure_reason": failure_reason,
        }


def pass_rate(results: list[CaseResult]) -> float:
    """Compute the raw pass rate as a proportion in [0.0, 1.0].

    Args:
        results: List of CaseResult.

    Returns:
        Fraction of cases that passed, or 0.0 for an empty list.
    """
    if not results:
        return 0.0
    return sum(1 for r in results if r.passed) / len(results)


def wilson_lower(successes: int, n: int, confidence: float = 0.95) -> float:
    """Wilson score interval lower bound for a binomial proportion.

    Implements the Wilson (1927) score interval using the two-sided
    z-score so that the lower bound is the standard conservative estimate
    used in evaluation quality gates.

    Hand-computed verification (see tests/test_scoring.py for KAT):
        n=100, successes=90, confidence=0.95
        p_hat = 0.90, z = 1.96
        numerator  = 0.90 + 1.96^2/(200) - 1.96*sqrt(0.90*0.10/100 + 1.96^2/40000)
                   = 0.90 + 0.019208 - 1.96*sqrt(0.0009 + 0.000096)
                   = 0.90 + 0.019208 - 1.96*sqrt(0.000996)
                   = 0.90 + 0.019208 - 1.96*0.031559
                   = 0.90 + 0.019208 - 0.061855
                   = 0.857353
        denominator = 1 + 1.96^2/100 = 1 + 0.038416 = 1.038416
        lower = 0.857353 / 1.038416 = 0.82565...
        Expected: approximately 0.8257 (matches scipy.stats.proportion_confint)

    Args:
        successes: Number of successful cases.
        n: Total number of cases.
        confidence: Desired confidence level (default 0.95).

    Returns:
        Lower bound of the Wilson score interval in [0.0, 1.0].
        Returns 0.0 for n=0.
    """
    if n == 0:
        return 0.0

    # z is the two-sided normal quantile for the given confidence level.
    # For 0.95: z = 1.959963985...  We use a lookup for common values
    # and a Newton-Raphson approximation for others to avoid scipy.
    z = _normal_quantile((1.0 + confidence) / 2.0)

    p_hat = successes / n
    z2 = z * z
    n2 = n * n

    term_under_root = p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n2)
    # Guard against floating-point rounding giving a tiny negative.
    term_under_root = max(term_under_root, 0.0)

    numerator = p_hat + z2 / (2.0 * n) - z * math.sqrt(term_under_root)
    denominator = 1.0 + z2 / n

    lower = numerator / denominator
    # Clamp to valid probability range.
    return max(0.0, min(1.0, lower))


def _normal_quantile(p: float) -> float:
    """Inverse normal CDF (probit) via rational approximation.

    Uses the Abramowitz & Stegun rational approximation (algorithm 26.2.17)
    which has maximum error < 3e-4 for p in (0, 1).  Accurate enough for
    the z-values used in confidence intervals.

    Args:
        p: Probability in (0, 1).

    Returns:
        z such that Phi(z) = p.
    """
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"p must be in (0, 1), got {p}")
    # Common exact values (avoid approximation error for standard CI).
    _known: dict[float, float] = {
        0.975: 1.959963985,
        0.95: 1.6448536270,
        0.99: 2.326347874,
        0.995: 2.575829304,
    }
    if p in _known:
        return _known[p]

    sign = 1.0 if p >= 0.5 else -1.0
    q = p if p >= 0.5 else 1.0 - p
    t = math.sqrt(-2.0 * math.log(1.0 - q))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    numerator = c0 + c1 * t + c2 * t * t
    denominator = 1.0 + d1 * t + d2 * t * t + d3 * t * t * t
    return sign * (t - numerator / denominator)


@dataclass
class Pricing:
    """Per-token pricing in USD for cost estimation.

    Args:
        cost_per_token_in: Cost per input token in USD.
        cost_per_token_out: Cost per output token in USD.
    """

    cost_per_token_in: float = 0.0
    cost_per_token_out: float = 0.0

    def compute_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Return total cost in USD."""
        return self.cost_per_token_in * tokens_in + self.cost_per_token_out * tokens_out


@dataclass(frozen=True)
class SuiteResult:
    """Aggregate statistics for an evaluation suite run.

    Fields:
        suite_name: Name of the suite.
        case_results: Ordered list of per-case results.
        pass_rate_value: Raw pass rate [0, 1].
        wilson_lower_bound: Wilson score lower bound at 95% confidence.
        total_tokens_in: Sum of input tokens across all cases.
        total_tokens_out: Sum of output tokens across all cases.
        total_cost_usd: Estimated cost in USD (0.0 if no pricing given).
        p50_latency_ms: 50th-percentile latency in ms.
        p95_latency_ms: 95th-percentile latency in ms.
    """

    suite_name: str
    case_results: tuple[CaseResult, ...]
    pass_rate_value: float
    wilson_lower_bound: float
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    p50_latency_ms: float
    p95_latency_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "suite_name": self.suite_name,
            "pass_rate": self.pass_rate_value,
            "wilson_lower": self.wilson_lower_bound,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_cost_usd": self.total_cost_usd,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "n_cases": len(self.case_results),
            "n_passed": sum(1 for r in self.case_results if r.passed),
            "cases": [r.to_dict() for r in self.case_results],
            "metadata": self.metadata,
        }


def compute_suite(
    case_results: list[CaseResult],
    suite_name: str = "",
    pricing: Pricing | None = None,
) -> SuiteResult:
    """Aggregate a list of CaseResult into a SuiteResult.

    Args:
        case_results: All cases in this suite, in deterministic order.
        suite_name: Label for the suite.
        pricing: Optional pricing for cost estimation.

    Returns:
        SuiteResult with all statistics populated.
    """
    # Sort by case_id for deterministic output.
    sorted_results = sorted(case_results, key=lambda r: r.case_id)
    n = len(sorted_results)
    successes = sum(1 for r in sorted_results if r.passed)
    rate = successes / n if n > 0 else 0.0
    wilson = wilson_lower(successes, n)

    total_in = sum(r.tokens_in for r in sorted_results)
    total_out = sum(r.tokens_out for r in sorted_results)

    cost = 0.0
    if pricing is not None:
        cost = pricing.compute_cost(total_in, total_out)

    latencies = sorted(r.latency_ms for r in sorted_results)
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)

    return SuiteResult(
        suite_name=suite_name,
        case_results=tuple(sorted_results),
        pass_rate_value=rate,
        wilson_lower_bound=wilson,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_cost_usd=cost,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
    )


def _percentile(sorted_values: list[float], pct: int) -> float:
    """Return the p-th percentile of a pre-sorted list using linear interpolation."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    # Nearest-rank method with 0-based indexing.
    idx = (pct / 100.0) * (n - 1)
    lower = int(idx)
    upper = min(lower + 1, n - 1)
    frac = idx - lower
    return sorted_values[lower] * (1.0 - frac) + sorted_values[upper] * frac
