"""Known-answer tests (KAT) for agenteval.scoring.

For each test, the fault it would detect is documented in the test's docstring.

Faults detected by this module:
- test_wilson_lower_n100_s90: catches a scoring.wilson_lower implementation that
  returns a value outside the hand-computed range [0.82, 0.84] for n=100, s=90.
  Fault injection: change the wilson_lower formula denominator to (1 + z2) instead
  of (1 + z2/n) => returns ~0.445, not ~0.826 => test fails.

- test_wilson_lower_n10_s10: catches an implementation that clips incorrectly at
  100% rather than computing a finite lower bound for perfect scores on small n.
  Fault injection: return 1.0 for s==n => returns 1.0, not ~0.718 => test fails.

- test_wilson_lower_n10_s0: catches an implementation that returns a negative lower
  bound instead of clamping to 0.0.
  Fault injection: remove the max(0.0, ...) clamp => may return slightly negative.

- test_wilson_lower_n0: catches an implementation that raises ZeroDivisionError
  instead of returning 0.0 for an empty sample.
  Fault injection: remove the 'if n == 0: return 0.0' guard.

- test_pass_rate_empty: catches an implementation that raises ZeroDivisionError on
  empty input instead of returning 0.0.

- test_pass_rate_all_pass: catches an off-by-one error in success counting.

- test_pass_rate_all_fail: catches a sign inversion in the pass/fail predicate.

- test_compute_suite_determinism: catches non-deterministic output (dict-ordering
  dependence) in compute_suite by running twice and comparing.

- test_percentile_p50: catches an incorrect percentile interpolation.

- test_compute_suite_cost: catches cost computation bugs when pricing is provided.

- test_wilson_lower_n5_s5: catches an implementation returning ~0.478 for
  wilson_lower(5, 5). The correct value is ~0.566. RESEARCH.md and
  ADVERSARIAL_REVIEW.md both stated 0.478 (wrong by ~9pp). The correct formula
  gives 1/(1 + z^2/n) for p_hat=1.0, which equals ~0.566 at z=1.96, n=5.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agenteval.assertions import CheckResults
from agenteval.scoring import (
    CaseResult,
    Pricing,
    _percentile,
    compute_suite,
    pass_rate,
    wilson_lower,
)


def _make_case(case_id: str, passed: bool) -> CaseResult:
    """Helper to build a minimal CaseResult."""
    return CaseResult(
        case_id=case_id,
        passed=passed,
        checks=CheckResults(results=()),
        tokens_in=10,
        tokens_out=5,
        latency_ms=100.0,
    )


class TestWilsonLower:
    """Known-answer tests for the Wilson score lower bound.

    Reference computation (n=100, successes=90, confidence=0.95):
        p_hat = 90/100 = 0.90
        z     = 1.959963985   (two-sided 95% normal quantile)
        z^2   = 3.841458...

        term_under_root = p_hat*(1-p_hat)/n + z^2/(4*n^2)
                       = 0.90*0.10/100 + 3.841458/(4*10000)
                       = 0.0009 + 0.00009604
                       = 0.00099604
        sqrt(...)       = 0.031558...

        numerator  = p_hat + z^2/(2n) - z*sqrt(...)
                   = 0.90 + 3.841458/200 - 1.959964*0.031558
                   = 0.90 + 0.019207 - 0.061854
                   = 0.857353

        denominator = 1 + z^2/n = 1 + 3.841458/100 = 1.038415

        lower = 0.857353 / 1.038415 = 0.82566...

    Verified against scipy.stats.proportion_confint(90, 100, alpha=0.05,
    method='wilson') lower bound = 0.8257 (to 4 d.p.).
    """

    def test_wilson_lower_n100_s90(self) -> None:
        """Fault detected: wrong wilson_lower formula (denominator error).

        Hand-computed lower bound: 0.82566 (see class docstring).
        Tolerance: ±0.005 (larger than floating-point error, smaller than formula error).
        """
        result = wilson_lower(successes=90, n=100, confidence=0.95)
        # Independently derived: 0.82566 (see class-level derivation above).
        expected = 0.82566
        assert abs(result - expected) < 0.005, (
            f"wilson_lower(90, 100) = {result:.5f}, expected ~{expected:.5f}. "
            "Check the denominator formula: must be (1 + z^2/n), not (1 + z^2)."
        )

    def test_wilson_lower_n10_s10(self) -> None:
        """Fault detected: returning 1.0 for perfect score on small n.

        For n=10, s=10: the Wilson lower bound is strictly less than 1.0
        because the formula accounts for uncertainty in a small sample.
        Hand-computed:
            p_hat=1.0, z=1.96, z^2=3.8416
            term_under_root = 0/(10) + 3.8416/400 = 0.009604
            sqrt = 0.098
            numerator = 1.0 + 3.8416/20 - 1.96*0.098 = 1.0 + 0.19208 - 0.19208 = 1.0
            denominator = 1 + 3.8416/10 = 1.38416
            lower = 1.0 / 1.38416 = 0.72245
        """
        result = wilson_lower(successes=10, n=10, confidence=0.95)
        expected = 0.722
        assert abs(result - expected) < 0.01, (
            f"wilson_lower(10, 10) = {result:.5f}, expected ~{expected:.5f}. "
            "Must not return 1.0 for s==n with small n."
        )

    def test_wilson_lower_n10_s0(self) -> None:
        """Fault detected: returning a negative lower bound for s=0.

        The lower bound must be clamped to [0, 1]; Wilson formula can
        produce a negative numerator for p_hat=0 with small n.
        """
        result = wilson_lower(successes=0, n=10, confidence=0.95)
        assert result >= 0.0, f"Lower bound must be >= 0, got {result}"
        # For s=0, hand-computed:
        #   numerator = 0 + z^2/20 - z*sqrt(z^2/400) = z^2/20 - z^2/20 = 0
        #   denominator > 1
        # => lower = 0.0 (or close to it after clamping)
        assert result < 0.1, f"Lower bound for s=0 should be near 0, got {result}"

    def test_wilson_lower_n0(self) -> None:
        """Fault detected: ZeroDivisionError when n=0 instead of returning 0.0."""
        result = wilson_lower(successes=0, n=0)
        assert result == 0.0, f"Expected 0.0 for n=0, got {result}"

    def test_wilson_lower_confidence_0_99(self) -> None:
        """Fault detected: confidence parameter ignored (always using z=1.96).

        At 99% confidence the lower bound must be strictly less than at 95%.
        """
        lower_95 = wilson_lower(successes=80, n=100, confidence=0.95)
        lower_99 = wilson_lower(successes=80, n=100, confidence=0.99)
        assert lower_99 < lower_95, (
            f"99% CI lower bound ({lower_99:.4f}) should be < "
            f"95% lower bound ({lower_95:.4f}) for the same data."
        )

    def test_wilson_lower_n5_s5(self) -> None:
        """Fault detected: returning 0.478 for wilson_lower(5, 5) instead of ~0.566.

        This KAT exists because the adversarial review (F3) and RESEARCH.md both
        claimed the value was 0.478 (~47.8%). The actual formula gives 0.5655 (~56.6%).
        The error was 9 percentage points — large enough to mislead any reader using
        this as a gate argument.

        Hand computation (n=5, s=5, p_hat=1.0, z=1.959963985):
            term_under_root = 1.0*(1.0-1.0)/5 + z^2/(4*25)
                            = 0 + 3.84158/(100)
                            = 0.0384158
            sqrt(...)       = 0.19601...

            numerator  = 1.0 + z^2/(2*5) - z*sqrt(...)
                       = 1.0 + 3.84158/10 - 1.959963985*0.19601
                       = 1.0 + 0.384158 - 0.384158
                       = 1.0
            denominator = 1 + z^2/5 = 1 + 0.768316 = 1.768316

            lower = 1.0 / 1.768316 = 0.56549...

        The key insight: for p_hat=1.0, the sqrt term equals z^2/(2n) exactly,
        so numerator always simplifies to 1.0, and the result is 1/(1 + z^2/n).
        This is strictly > 0.5 for any finite n with z=1.96.

        The wrong value 0.478 would arise from using z=1.64 (one-sided 95%) or
        from a denominator error — both are detectable by this test.
        """
        result = wilson_lower(successes=5, n=5, confidence=0.95)
        expected = 0.5655
        assert abs(result - expected) < 0.005, (
            f"wilson_lower(5, 5) = {result:.4f}, expected ~{expected:.4f}. "
            "RESEARCH.md and ADVERSARIAL_REVIEW.md claimed 0.478, which is wrong. "
            "See hand computation in this docstring."
        )
        # Must be strictly greater than 0.5 (the halfway point) — a common wrong
        # implementation that returns <0.5 for perfect small-n scores is caught here.
        assert result > 0.5, (
            f"wilson_lower(5, 5) = {result:.4f} should be > 0.5; "
            "an implementation returning <0.5 for 5/5 is incorrect."
        )


class TestPassRate:
    """KAT for the pass_rate function."""

    def test_pass_rate_empty(self) -> None:
        """Fault detected: ZeroDivisionError for empty input."""
        assert pass_rate([]) == 0.0

    def test_pass_rate_all_pass(self) -> None:
        """Fault detected: off-by-one error in success counting."""
        cases = [_make_case(str(i), True) for i in range(5)]
        assert pass_rate(cases) == 1.0

    def test_pass_rate_all_fail(self) -> None:
        """Fault detected: sign inversion in pass/fail predicate."""
        cases = [_make_case(str(i), False) for i in range(5)]
        assert pass_rate(cases) == 0.0

    def test_pass_rate_mixed(self) -> None:
        """Fault detected: incorrect numerator or denominator in ratio."""
        cases = [_make_case(str(i), i < 3) for i in range(5)]
        assert pass_rate(cases) == 0.6


class TestPercentile:
    """KAT for the internal _percentile function."""

    def test_percentile_p50_even(self) -> None:
        """Fault detected: incorrect linear interpolation for even-length list."""
        values = [10.0, 20.0, 30.0, 40.0]
        # p=50: idx = 0.5*3 = 1.5 => lower=1 (20.0), upper=2 (30.0), frac=0.5
        # => 20.0*0.5 + 30.0*0.5 = 25.0
        result = _percentile(values, 50)
        assert result == 25.0, f"p50 of [10,20,30,40] should be 25.0, got {result}"

    def test_percentile_p95(self) -> None:
        """Fault detected: wrong p95 clipping (returns max instead of interpolating)."""
        values = [float(i) for i in range(1, 21)]  # 1..20
        # p=95: idx = 0.95*19 = 18.05 => lower=18 (19.0), upper=19 (20.0)
        # => 19.0*0.95 + 20.0*0.05 = 18.05 + 1.0 = 19.05
        result = _percentile(values, 95)
        assert abs(result - 19.05) < 0.01, f"p95 expected ~19.05, got {result}"

    def test_percentile_empty(self) -> None:
        """Fault detected: crash on empty list instead of returning 0.0."""
        assert _percentile([], 50) == 0.0

    def test_percentile_single(self) -> None:
        """Fault detected: index error for single-element list."""
        assert _percentile([42.0], 95) == 42.0


class TestComputeSuite:
    """Integration KAT for compute_suite."""

    def test_compute_suite_determinism(self) -> None:
        """Fault detected: non-deterministic output ordering (dict-order dependence).

        Two identical calls must produce byte-identical JSON serialisation.
        """
        import json

        cases = [_make_case(str(i), i % 2 == 0) for i in range(6)]
        s1 = compute_suite(cases, suite_name="test")
        s2 = compute_suite(cases, suite_name="test")
        assert json.dumps(s1.to_dict()) == json.dumps(
            s2.to_dict()
        ), "compute_suite output is not deterministic — check sort order."

    def test_compute_suite_cost(self) -> None:
        """Fault detected: pricing not applied to token counts."""
        cases = [
            CaseResult(
                case_id="a",
                passed=True,
                checks=CheckResults(results=()),
                tokens_in=100,
                tokens_out=50,
                latency_ms=200.0,
            )
        ]
        pricing = Pricing(cost_per_token_in=0.001, cost_per_token_out=0.002)
        suite = compute_suite(cases, pricing=pricing)
        expected_cost = 0.001 * 100 + 0.002 * 50
        assert (
            abs(suite.total_cost_usd - expected_cost) < 1e-9
        ), f"Cost mismatch: expected {expected_cost}, got {suite.total_cost_usd}"

    def test_compute_suite_pass_rate_and_wilson(self) -> None:
        """Fault detected: wilson_lower inconsistent with pass_rate on known input."""
        cases = [_make_case(str(i), i < 90) for i in range(100)]
        suite = compute_suite(cases)
        assert abs(suite.pass_rate_value - 0.9) < 1e-9
        # Wilson lower bound for 90/100 at 95% is ~0.826 (see KAT above).
        assert (
            0.82 < suite.wilson_lower_bound < 0.84
        ), f"wilson_lower for 90/100 expected ~0.826, got {suite.wilson_lower_bound}"
