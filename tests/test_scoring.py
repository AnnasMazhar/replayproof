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

- test_percentile_n2: catches a mutant that changes the 'n == 1' early-return guard
  to 'n == 2', which would return sorted_values[0] (the minimum) for a 2-element
  list at any percentile. For p50 of [1.0, 3.0], the correct answer is 2.0 (midpoint
  via interpolation); the n==2 mutant returns 1.0 (minimum).

- test_compute_suite_name_preserved: catches mutations to the suite_name default or
  string concatenation in metadata. The suite name must round-trip through to_dict().

TestWilsonLowerConfidenceValidation (new, C2P11-MAJ-1):
- test_wilson_lower_rejects_negative_confidence: catches wilson_lower(3, 5, -0.5)
  returning a garbage float (0.733) instead of raising ValueError.  The adversarial
  review found this returned 0.733332 silently.
- test_wilson_lower_rejects_zero_confidence: catches confidence=0 edge.
- test_wilson_lower_rejects_confidence_geq_1: catches confidence>=1 edge.
- test_wilson_lower_accepts_095_confidence: verifies the guard does not break the
  standard 95% confidence value.

TestWilsonLowerKATSmallN (new, c5-p04):
- test_wilson_lower_n10_s1_hand_computed: KAT for s=1, n=10 at 95% confidence.
  Hand derivation (matches repo to 6dp):
    z=1.959964, z²=3.841459, p̂=0.10
    denom = 1 + 3.841459/10 = 1.384146
    centre = (0.10 + 3.841459/20) / 1.384146 = 0.211013
    term = 0.10·0.90/10 + 3.841459/(4·100) = 0.009 + 0.009604 = 0.018604
    half = 1.959964·√0.018604 / 1.384146 = 0.193137
    lower = 0.211013 - 0.193137 = 0.017876
  Fault injection: forget to divide term_under_root addition by n² in the second
  addend → lower becomes negative → max(0.0, ...) clamps to 0.0 → test fails.

- test_wilson_lower_n20_s3_hand_computed: KAT for s=3, n=20 at 95% confidence.
  Hand derivation:
    z=1.959964, z²=3.841459, p̂=0.15
    denom = 1 + 3.841459/20 = 1.192073
    centre = (0.15 + 3.841459/40) / 1.192073 = (0.15 + 0.096036) / 1.192073 = 0.206377
    term = 0.15·0.85/20 + 3.841459/(4·400) = 0.006375 + 0.002401 = 0.008776
    half = 1.959964·√0.008776 / 1.192073 = 0.154008
    lower = 0.206377 - 0.154008 = 0.052369
  Fault injection: wrong p_hat = (successes+1)/n instead of successes/n → centre is
  larger → lower is 0.107 instead of 0.052 → assertion fails.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agenteval.assertions import CheckResults
from agenteval.scoring import (
    CaseResult,
    Pricing,
    _normal_quantile,
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

    def test_percentile_p100_at_last_element(self) -> None:
        """Fault: mutmut_22 changes 'upper = min(lower+1, n-1)' to 'min(lower+1, n+1)'.

        At p=100 on a 5-element list: rank = 100/100 * 4 = 4.0 (the last index).
        lower = 4, upper = min(5, n-1=4) = 4 (correct: clamp to last element).
        With mutant: upper = min(5, n+1=6) = 5 => values[5] => IndexError.
        This test kills the mutant by accessing p=100 (rank at the last element).
        """
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = _percentile(values, 100)
        assert result == 50.0, f"p100 of [10..50] should be 50.0 (last element), got {result}"


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

    def test_percentile_n2(self) -> None:
        """Fault detected: mutant changes 'n == 1' early-return guard to 'n == 2'.

        If n == 2 triggered the early return, _percentile([1.0, 3.0], 50) would
        return sorted_values[0] = 1.0 instead of the interpolated midpoint 2.0.

        Hand computation:
            sorted = [1.0, 3.0], n = 2
            idx = (50/100) * (2-1) = 0.5
            lower = int(0.5) = 0,  upper = 1,  frac = 0.5
            result = 1.0 * 0.5 + 3.0 * 0.5 = 2.0
        """
        result = _percentile([1.0, 3.0], 50)
        assert result == 2.0, f"p50 of [1.0, 3.0] should be 2.0 (midpoint), got {result}"

    def test_compute_suite_name_preserved(self) -> None:
        """Fault detected: mutations to suite_name default or string handling.

        The suite name must round-trip intact through to_dict() with no truncation,
        concatenation, or substitution.
        """
        cases = [_make_case("x", True)]
        suite = compute_suite(cases, suite_name="cycle2-test-suite")
        assert (
            suite.to_dict()["suite_name"] == "cycle2-test-suite"
        ), f"suite_name not preserved: {suite.to_dict()['suite_name']}"


class TestWilsonLowerInputValidation:
    """Tests for AR2-MIN-2 fix: wilson_lower rejects invalid inputs.

    Faults detected:
    - test_wilson_lower_rejects_successes_gt_n: catches implementations that
      silently accept successes > n (returns nonsensical or clamped value).
      Fault injection: remove the validation guard => test fails (no ValueError raised).
    - test_wilson_lower_rejects_negative_successes: catches implementations that
      accept negative success counts.
    """

    def test_wilson_lower_rejects_successes_gt_n(self) -> None:
        """Fault: wilson_lower(10, 5) returns a value instead of raising.

        successes=10 with n=5 is physically impossible (more successes than trials).
        The adversarial review (AR2-MIN-2) showed this returned 1.0 silently.
        After fix: must raise ValueError.
        """
        with pytest.raises(ValueError, match="successes.*<=.*n|more successes than total"):
            wilson_lower(10, 5, 0.95)

    def test_wilson_lower_rejects_negative_successes(self) -> None:
        """Fault: wilson_lower(-1, 5) accepts negative success count."""
        with pytest.raises(ValueError, match="successes.*>=.*0"):
            wilson_lower(-1, 5, 0.95)

    def test_wilson_lower_accepts_zero_successes(self) -> None:
        """Boundary: successes=0 is valid (0/n = 0% pass rate).

        This must NOT raise — it is a legal input.
        Hand computation: p_hat=0, lower bound approaches 0 for large n.
        """
        result = wilson_lower(0, 10, 0.95)
        assert 0.0 <= result < 0.1, f"wilson_lower(0, 10) should be near 0, got {result}"

    def test_wilson_lower_accepts_n_eq_successes(self) -> None:
        """Boundary: successes == n is valid (100% pass rate).

        Must NOT raise — the validated edge case from c1-p08.
        """
        result = wilson_lower(5, 5, 0.95)
        assert abs(result - 0.5655) < 0.001, f"wilson_lower(5, 5) should be ~0.5655, got {result}"


class TestWilsonLowerConfidenceValidation:
    """Tests for C2P11-MAJ-1 fix: wilson_lower rejects negative/invalid confidence.

    Root cause: the function previously only validated successes and n but
    did not check confidence.  A negative confidence value is fed to
    _normal_quantile, which computes (1 + confidence) / 2 — a value in (0, 0.5)
    for negative confidence — and returns a negative z.  The formula then
    produces a number that looks plausible but is mathematically meaningless.
    The function must fail-closed: if confidence is not in (0, 1), raise.

    Faults detected:
    - test_wilson_lower_rejects_negative_confidence: catches implementations
      that accept negative confidence and return a value.
      Fault injection: remove the `if not (0 < confidence < 1)` guard =>
      wilson_lower(3, 5, -0.5) = 0.733 (garbage, not an error) => test fails.
    - test_wilson_lower_rejects_zero_confidence: catches confidence=0 edge.
    - test_wilson_lower_rejects_confidence_geq_1: catches confidence>=1 edge.
    - test_wilson_lower_accepts_boundary_confidence_values: verifies common
      valid values still work after adding the guard.
    """

    def test_wilson_lower_rejects_negative_confidence(self) -> None:
        """Fault: wilson_lower(3, 5, -0.5) returns 0.733 instead of raising (C2P11-MAJ-1).

        The adversarial review showed: wilson_lower(3, 5, -0.5) = 0.733332
        and labeled it a vulnerability.  After fix: must raise ValueError.
        """
        with pytest.raises(ValueError, match="confidence.*\\(0, 1\\)|confidence must be"):
            wilson_lower(3, 5, -0.5)

    def test_wilson_lower_rejects_small_negative_confidence(self) -> None:
        """Fault: small negative confidence accepted, producing garbage z-score."""
        with pytest.raises(ValueError, match="confidence"):
            wilson_lower(3, 5, -0.1)

    def test_wilson_lower_rejects_zero_confidence(self) -> None:
        """Fault: confidence=0 accepted; z=_normal_quantile(0.5)=0, lower=p_hat (wrong)."""
        with pytest.raises(ValueError, match="confidence"):
            wilson_lower(3, 5, 0.0)

    def test_wilson_lower_rejects_confidence_one(self) -> None:
        """Fault: confidence=1.0 accepted; z=inf, lower approaches 0 or NaN."""
        with pytest.raises(ValueError, match="confidence"):
            wilson_lower(3, 5, 1.0)

    def test_wilson_lower_rejects_confidence_gt_one(self) -> None:
        """Fault: confidence=1.5 accepted; (1+1.5)/2=1.25 -> _normal_quantile raises."""
        with pytest.raises(ValueError, match="confidence"):
            wilson_lower(3, 5, 1.5)

    def test_wilson_lower_accepts_095_confidence(self) -> None:
        """Boundary: 0.95 is the standard value and must still work after the guard."""
        result = wilson_lower(90, 100, 0.95)
        assert abs(result - 0.82566) < 0.005

    def test_wilson_lower_accepts_099_confidence(self) -> None:
        """Boundary: 0.99 is another standard value; must still work."""
        result = wilson_lower(90, 100, 0.99)
        assert 0.0 < result < 0.82566  # 99% CI lower bound is tighter


class TestNormalQuantile:
    """Direct KATs for _normal_quantile (probit / inverse-CDF) to kill surviving mutants.

    _normal_quantile is only reached via wilson_lower when the confidence value
    maps to a p not in the _known lookup.  Most surviving mutants are in the
    Abramowitz & Stegun coefficients (c0, c1, c2, d1, d2, d3) and in the
    boundary guard.  These tests exercise those paths directly.

    Published reference values:
        Standard normal quantile z such that Phi(z) = p.
        z(0.975) = 1.9599639845...   (exact; in _known lookup)
        z(0.95)  = 1.6448536270...   (exact; in _known lookup)
        z(0.99)  = 2.3263478740...   (exact; in _known lookup)
        z(0.995) = 2.5758293040...   (exact; in _known lookup)
        z(0.90)  ≈ 1.2815516        (Abramowitz & Stegun max error < 3e-4)
        z(0.80)  ≈ 0.8415            (A&S approximation; symmetry partner at 0.20)
    Source: Abramowitz & Stegun (1964), Handbook of Mathematical Functions,
    formula 26.2.17, p.933.
    """

    def test_normal_quantile_boundary_zero(self) -> None:
        """Fault: p=0.0 accepted because guard uses p < 0.0 instead of p <= 0.0.

        Injection: change guard to 'if p < 0.0 or p >= 1.0' => p=0.0 not caught =>
        log(1-q) = log(1) = 0 => t=0 => returns -(c0/1) = -2.515 (wrong sign, not
        infinity).  Test must see ValueError, not a garbage float.
        """
        with pytest.raises(ValueError):
            _normal_quantile(0.0)

    def test_normal_quantile_boundary_one(self) -> None:
        """Fault: p=1.0 accepted (log(0) => math.log raises ValueError in Python)."""
        with pytest.raises((ValueError, OverflowError)):
            _normal_quantile(1.0)

    def test_normal_quantile_known_lookup_0975(self) -> None:
        """KAT: z(0.975) must equal the exact value stored in the _known dict.

        Mutation: change 1.959963985 to any other float => test fails.
        Published: Wilson (1927) uses z=1.96; exact = 1.959963985... per standard tables.
        """
        z = _normal_quantile(0.975)
        # Exact value from the dict; any coefficient mutation that reaches the
        # approximation path would return a different value (~1.96 from A&S).
        assert abs(z - 1.959963985) < 1e-9, f"Expected 1.959963985, got {z}"

    def test_normal_quantile_known_lookup_095(self) -> None:
        """KAT: z(0.95) from lookup must equal 1.6448536270.

        Mutation: change key 0.95 → 1.95 => miss the lookup => fall through to
        approximation => returns ~1.645 via A&S (close but != 1.6448536270).
        Mutation: change value 1.6448536270 → 2.644... => obvious mismatch.
        """
        z = _normal_quantile(0.95)
        assert abs(z - 1.6448536270) < 1e-9, f"Expected 1.6448536270, got {z}"

    def test_normal_quantile_known_lookup_099(self) -> None:
        """KAT: z(0.99) from lookup must equal 2.326347874.

        Mutation: key 0.99 → 1.99 => lookup miss => A&S returns a different value.
        """
        z = _normal_quantile(0.99)
        assert abs(z - 2.326347874) < 1e-9, f"Expected 2.326347874, got {z}"

    def test_normal_quantile_known_lookup_0995(self) -> None:
        """KAT: z(0.995) from lookup must equal 2.575829304.

        Mutation: key 0.995 → 1.995 => lookup miss.
        """
        z = _normal_quantile(0.995)
        assert abs(z - 2.575829304) < 1e-9, f"Expected 2.575829304, got {z}"

    def test_normal_quantile_lookup_not_in_keys(self) -> None:
        """Fault: 'p not in _known' inversion causes lookup miss for every valid key.

        Mutation: 'if p in _known' → 'if p not in _known' => p=0.975 falls through
        to the A&S approximation and returns ~1.96 instead of the exact 1.959963985.
        p=0.90 (not in _known) must still return a finite value close to 1.282.
        This test checks the non-lookup path is reached for p=0.90.
        """
        z = _normal_quantile(0.90)
        # A&S formula 26.2.17: max error < 3e-4.  Published value: 1.281552.
        assert abs(z - 1.28155) < 5e-4, f"Expected ~1.28155, got {z}"

    def test_normal_quantile_approx_090(self) -> None:
        """KAT: z(0.90) exercises the A&S approximation path.

        Any mutation to c0, c1, c2, d1, d2, or d3 changes the output by at least 0.01.
        Published: Abramowitz & Stegun (1964) formula 26.2.17 — z(0.90) ≈ 1.28155.
        """
        z = _normal_quantile(0.90)
        # Tolerance 5e-4 (A&S formula max error is < 3e-4; 5e-4 gives margin).
        assert abs(z - 1.28155) < 5e-4, f"Expected ~1.28155, got {z}"

    def test_normal_quantile_approx_080(self) -> None:
        """KAT: z(0.80) — second independent coefficient-coverage test.

        Published: z(0.80) ≈ 0.84162 from standard normal tables.
        """
        z = _normal_quantile(0.80)
        assert abs(z - 0.84162) < 5e-4, f"Expected ~0.84162, got {z}"

    def test_normal_quantile_negative_branch(self) -> None:
        """Fault: sign branch mutations cause p<0.5 to return positive z.

        Mutation: 'sign = 1.0 if p >= 0.5 else -1.0' → constant +1.0 =>
        _normal_quantile(0.10) = +1.282 instead of -1.282.
        """
        z = _normal_quantile(0.10)
        assert z < 0, f"z({0.10}) must be negative, got {z}"
        # By symmetry: _normal_quantile(0.10) = -_normal_quantile(0.90)
        z_sym = _normal_quantile(0.90)
        assert abs(z + z_sym) < 1e-10, f"Symmetry broken: z(0.1)={z}, -z(0.9)={z_sym}"

    def test_normal_quantile_symmetry(self) -> None:
        """Property: _normal_quantile(p) = -_normal_quantile(1-p) for all valid p.

        Catches sign-flip mutations in the return expression.
        """
        for p in [0.60, 0.70, 0.80, 0.90]:
            z_p = _normal_quantile(p)
            z_mirror = _normal_quantile(1.0 - p)
            assert (
                abs(z_p + z_mirror) < 1e-10
            ), f"Symmetry broken at p={p}: z(p)={z_p}, z(1-p)={z_mirror}"


class TestComputeSuiteEdgeCases:
    """Edge-case KATs for compute_suite to kill surviving mutants.

    Faults detected:
    - test_compute_suite_empty_gives_zero_pass_rate: catches 'n >= 0' mutant
      (mutmut_14: changes 'n > 0' to 'n >= 0' — no observable effect for n=0
      since both evaluate the same when n is exactly 0; BUT 'n > 0' is the
      correct guard and 'n >= 0' with n=0 still divides by zero — the mutant
      would raise ZeroDivisionError on an empty list).
    - test_compute_suite_empty_gives_zero_cost: catches cost initialisation
      mutation (mutmut_27: cost=0.0 → cost=1.0 => empty suite returns cost=1.0).
    - test_compute_suite_p50_and_p95_differ: catches latency percentile bugs
      where p50 and p95 are confused or constants are swapped (mutmut_41, _47).
    - test_wilson_lower_clamp_upper_at_one: catches min(2.0, lower) mutation
      (mutmut_69: min(1.0, ...) → min(2.0, ...) => lower bounds > 1.0 pass
      through unclipped).  For valid inputs lower is always <= 1.0, so this is
      an equivalent mutant — documented below.
    """

    def test_compute_suite_empty_gives_zero_pass_rate(self) -> None:
        """Fault: empty case list causes ZeroDivisionError (n > 0 guard absent).

        Mutation mutmut_14 changes 'n > 0' to 'n >= 0'; when n=0 the condition
        'n >= 0' is still True, so 0/0 is attempted => ZeroDivisionError.
        This test catches that by verifying empty input returns 0.0, not an error.
        """
        suite = compute_suite([], suite_name="empty")
        assert suite.pass_rate_value == 0.0, f"Expected 0.0 pass rate, got {suite.pass_rate_value}"
        assert suite.wilson_lower_bound == 0.0

    def test_compute_suite_empty_gives_zero_cost(self) -> None:
        """Fault: cost initialised to 1.0 instead of 0.0 (mutmut_27).

        An empty suite with no pricing must produce cost=0.0, not 1.0.
        """
        suite = compute_suite([], suite_name="empty_cost")
        assert suite.total_cost_usd == 0.0, f"Expected 0.0 cost, got {suite.total_cost_usd}"

    def test_compute_suite_p50_and_p95_differ(self) -> None:
        """Fault: p50 and p95 args to _percentile are swapped (mutmut_41: 51, mutmut_47: 96).

        10 cases with latencies 10, 20, ..., 100ms.
        Exact values (linear interpolation):
            p50: rank = 50/100 * 9 = 4.5 => vals[4] + 0.5*(vals[5]-vals[4]) = 50 + 5 = 55.0
            p95: rank = 95/100 * 9 = 8.55 => vals[8] + 0.55*(vals[9]-vals[8]) = 90 + 5.5 = 95.5
        With mutmut_41 (arg=51): rank=4.59 => 55.9 (not 55.0) => assertion fails.
        With mutmut_47 (arg=96): rank=8.64 => 96.4 (not 95.5) => assertion fails.
        """
        cases = [
            CaseResult(
                case_id=f"c{i}",
                passed=True,
                checks=CheckResults(results=()),
                tokens_in=0,
                tokens_out=0,
                latency_ms=float(i * 10),
            )
            for i in range(1, 11)  # 10, 20, 30, 40, 50, 60, 70, 80, 90, 100
        ]
        suite = compute_suite(cases, suite_name="latency_test")
        # Exact p50: 55.0ms (linear interpolation at rank 4.5 of sorted [10..100])
        assert abs(suite.p50_latency_ms - 55.0) < 0.5, (
            f"p50 expected ~55.0ms, got {suite.p50_latency_ms} " f"(mutmut_41 would give 55.9)"
        )
        # Exact p95: 95.5ms (rank 8.55)
        assert abs(suite.p95_latency_ms - 95.5) < 0.5, (
            f"p95 expected ~95.5ms, got {suite.p95_latency_ms} " f"(mutmut_47 would give 96.4)"
        )

    def test_wilson_lower_clamp_upper_at_one(self) -> None:
        """Equivalent-mutant documentation: min(1.0, lower) vs min(2.0, lower).

        The mutant changes min(1.0, lower) to min(2.0, lower).  For any valid
        call (0 <= successes <= n, n > 0), lower is provably in [0.0, 1.0]:
        p_hat is in [0, 1], and the Wilson formula cannot produce lower > 1.0.
        Therefore this mutant is equivalent — no test can kill it without an
        invalid input.

        This test documents that the existing clamp is defensive (belt-and-suspenders)
        and that the mutant is equivalent by exercising the maximum attainable lower.
        """
        # p_hat = 1.0 with large n gives lower close to (but below) 1.0.
        lower = wilson_lower(1000, 1000)
        assert lower <= 1.0, f"lower must be <= 1.0, got {lower}"
        # And the clamp doesn't truncate any real value.
        assert lower > 0.99, f"Expected lower near 1.0 for n=1000 all-pass, got {lower}"


class TestWilsonLowerKATSmallN:
    """Known-answer tests for wilson_lower at small n with published hand derivations.

    Both values were independently derived from the Wilson (1927) formula using
    stdlib NormalDist only — no repo code in the derivation path.

    Fault caught by test_wilson_lower_n10_s1_hand_computed:
    - An implementation that uses the wrong addend for term_under_root (divides by
      n instead of n² for the z²/(4n²) term) produces a larger term_under_root and
      a negative lower before the clamp, yielding 0.0 instead of ~0.0179.

    Fault caught by test_wilson_lower_n20_s3_hand_computed:
    - An implementation that uses p_hat = (successes+1)/n (off-by-one Laplace
      smoothing) shifts the centre and produces ~0.107 instead of ~0.052.
    """

    def test_wilson_lower_n10_s1_hand_computed(self) -> None:
        """KAT: wilson_lower(1, 10, 0.95) ≈ 0.0179 (hand derivation).

        Step-by-step derivation:
          z = 1.959964 (from NormalDist().inv_cdf(0.975))
          z² = 3.841459
          p̂ = 1/10 = 0.10
          denom    = 1 + 3.841459/10 = 1.384146
          centre   = (0.10 + 3.841459/20) / 1.384146
                   = (0.10 + 0.192073) / 1.384146
                   = 0.292073 / 1.384146
                   = 0.211013
          term     = 0.10·0.90/10 + 3.841459/(4·100)
                   = 0.009000 + 0.009604
                   = 0.018604
          half     = 1.959964·√0.018604 / 1.384146
                   = 1.959964·0.136399 / 1.384146
                   = 0.267338 / 1.384146
                   = 0.193137
          lower    = 0.211013 − 0.193137 = 0.017876
        Verified: python3 -c "from agenteval.scoring import wilson_lower;
                  print(f'{wilson_lower(1,10):.6f}')" → 0.017876
        """
        result = wilson_lower(1, 10, 0.95)
        # Tolerance 0.001 — a formula-level error shifts by >> 0.01
        assert abs(result - 0.017876) < 0.001, (
            f"wilson_lower(1, 10, 0.95) expected ~0.017876, got {result:.6f}. "
            "Hand derivation: z=1.96, p̂=0.1, denom=1.384, centre=0.211, half=0.193 → lower=0.018."
        )

    def test_wilson_lower_n20_s3_hand_computed(self) -> None:
        """KAT: wilson_lower(3, 20, 0.95) ≈ 0.0524 (hand derivation).

        Step-by-step derivation:
          z = 1.959964
          z² = 3.841459
          p̂ = 3/20 = 0.15
          denom    = 1 + 3.841459/20 = 1.192073
          centre   = (0.15 + 3.841459/40) / 1.192073
                   = (0.15 + 0.096036) / 1.192073
                   = 0.246036 / 1.192073
                   = 0.206377
          term     = 0.15·0.85/20 + 3.841459/(4·400)
                   = 0.006375 + 0.002401
                   = 0.008776
          half     = 1.959964·√0.008776 / 1.192073
                   = 1.959964·0.093681 / 1.192073
                   = 0.183614 / 1.192073
                   = 0.154008
          lower    = 0.206377 − 0.154008 = 0.052369
        Verified: python3 -c "from agenteval.scoring import wilson_lower;
                  print(f'{wilson_lower(3,20):.6f}')" → 0.052369
        """
        result = wilson_lower(3, 20, 0.95)
        assert abs(result - 0.052369) < 0.001, (
            f"wilson_lower(3, 20, 0.95) expected ~0.052369, got {result:.6f}. "
            "Hand derivation: z=1.96, p̂=0.15, denom=1.192, centre=0.206, half=0.154 → lower=0.052."
        )
