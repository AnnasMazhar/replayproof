"""Regression gates that compare a current SuiteResult against a stored baseline.

A baseline is a persisted SuiteResult dict (JSON).  The gate trips if ANY
metric degrades beyond its configured tolerance.

Zero-baseline behaviour: when a baseline metric is exactly zero, the
percentage-increase gate for that metric cannot compute a meaningful ratio and
is skipped.  This is expected on the first run (no prior data).  The skipped
gates are recorded in GateReport.skipped_zero_baseline so callers can surface
them in CI output and avoid silent pass-throughs on corrupted baselines.

Non-finite metric behaviour: if any float metric extracted from the current
dict is NaN or infinite, compare() raises ValueError immediately.  A corrupted
run file containing NaN/inf must never silently pass the gate — the gate's core
safety property is that it fails closed on bad input, not open.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GateTripDetail:
    """Details of a single tripped gate metric."""

    metric: str
    baseline_value: float
    current_value: float
    threshold: float
    direction: str  # "drop" or "increase"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "metric": self.metric,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class GateReport:
    """Result of comparing current metrics against a baseline.

    Fields:
        ok: True if all gates pass (no regression).
        trips: List of tripped gate details.
        skipped_zero_baseline: Names of percentage gates that were skipped
            because the baseline value was zero.  These gates are NOT enforced;
            callers should surface this list in CI output so a corrupted or
            empty baseline does not silently disable regression detection.
    """

    ok: bool
    trips: tuple[GateTripDetail, ...]
    skipped_zero_baseline: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "ok": self.ok,
            "trips": [t.to_dict() for t in self.trips],
            "skipped_zero_baseline": list(self.skipped_zero_baseline),
        }


@dataclass
class Tolerances:
    """Configurable tolerance thresholds for regression gates.

    All 'increase' thresholds are fractions (0.10 = 10% increase allowed).
    pass_rate_drop is an absolute drop (0.0 = no drop allowed).
    """

    max_pass_rate_drop: float = 0.0
    max_token_increase_pct: float = 0.10
    max_latency_increase_pct: float = 0.25
    max_cost_increase_pct: float = 0.10


def _finite_number(value: Any, name: str) -> float:
    """Coerce *value* to float, rejecting NaN/inf/non-numbers.

    A NaN metric silently passes every relational comparison (``nan > x`` is
    False), so a corrupted baseline or current file would otherwise report
    ``ok=True``. The gate must fail loudly instead.
    """
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"gate metric {name} is not a number: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"gate metric {name} is not a finite number: {number!r}")
    return number


class Baseline:
    """A stored SuiteResult used as the reference point for gate comparison.

    Args:
        data: Dict produced by ``SuiteResult.to_dict()``.

    Raises:
        ValueError: From any metric property, when the stored value is
            NaN/inf (or not a number). Corrupted baselines must fail loudly
            instead of silently disabling gates.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @classmethod
    def from_json(cls, text: str) -> Baseline:
        """Load from a JSON string."""
        return cls(json.loads(text))

    @classmethod
    def from_file(cls, path: str) -> Baseline:
        """Load from a JSON file path."""
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    @property
    def pass_rate(self) -> float:
        """Baseline pass rate."""
        return _finite_number(self._data.get("pass_rate", 0.0), "baseline.pass_rate")

    @property
    def total_tokens(self) -> int:
        """Baseline total tokens (in + out)."""
        tokens_in = _finite_number(self._data.get("total_tokens_in", 0), "baseline.total_tokens_in")
        tokens_out = _finite_number(
            self._data.get("total_tokens_out", 0), "baseline.total_tokens_out"
        )
        return int(tokens_in) + int(tokens_out)

    @property
    def p95_latency_ms(self) -> float:
        """Baseline p95 latency in ms."""
        return _finite_number(self._data.get("p95_latency_ms", 0.0), "baseline.p95_latency_ms")

    @property
    def total_cost_usd(self) -> float:
        """Baseline total cost in USD."""
        return _finite_number(self._data.get("total_cost_usd", 0.0), "baseline.total_cost_usd")


def compare(
    current: dict[str, Any],
    baseline: Baseline,
    tolerances: Tolerances | None = None,
) -> GateReport:
    """Compare current metrics against the baseline and return a GateReport.

    Percentage-increase gates (tokens, latency, cost) are skipped when the
    baseline value is zero — the ratio is undefined, typically meaning this is
    the first run.  Skipped gates are listed in GateReport.skipped_zero_baseline
    so CI can surface them rather than silently passing.

    Non-finite values in ``current`` raise ValueError immediately — the gate
    must fail closed on corrupted run files, not silently return ok=True.

    Args:
        current: Dict produced by ``SuiteResult.to_dict()``.
        baseline: The stored Baseline to compare against.
        tolerances: Gate thresholds; defaults to Tolerances() if not given.

    Returns:
        GateReport with ok=True if all enforced gates pass.

    Raises:
        ValueError: If any current or baseline metric is NaN/inf or not a
            number. Such input means a corrupted file, not a regression, and
            must never be scored as a pass.
    """
    tol = tolerances if tolerances is not None else Tolerances()
    trips: list[GateTripDetail] = []
    skipped: list[str] = []

    # Guard: reject corrupted run files that contain NaN or infinite values.
    # NaN comparisons always return False, so `drop > threshold` would be False
    # for a NaN pass_rate — silently returning ok=True on a corrupted file.
    _float_metrics = ("pass_rate", "p95_latency_ms", "total_cost_usd")
    for _metric in _float_metrics:
        _val = current.get(_metric)
        if _val is not None:
            _fval = float(_val)
            if not math.isfinite(_fval):
                raise ValueError(
                    f"current['{_metric}'] is not finite ({_fval!r}); "
                    "corrupted run files must not be passed to the gate"
                )

    # Guard: pass_rate must be in [0.0, 1.0].  A value outside this range can
    # only arise from a corrupted or hand-crafted run file.  Critically, a
    # pass_rate > 1.0 causes the drop calculation (baseline - current) to yield
    # a negative value, which is never > max_pass_rate_drop, so the gate
    # silently returns ok=True even though the value is physically impossible.
    _pr_val = current.get("pass_rate")
    if _pr_val is not None:
        _pr = float(_pr_val)
        if math.isfinite(_pr) and not (0.0 <= _pr <= 1.0):
            raise ValueError(f"current['pass_rate'] is {_pr!r}; pass_rate must be in [0.0, 1.0]")

    # Guard: reject negative token/cost/latency counts.  A negative token count
    # can only arise from a corrupted or hand-crafted run file.  Allowing it
    # silently would make the token-increase gate pass (negative < baseline,
    # so the delta is negative and the threshold check is never tripped).
    _nonneg_int_metrics = ("total_tokens_in", "total_tokens_out")
    for _metric in _nonneg_int_metrics:
        _val = current.get(_metric)
        if _val is not None:
            _ival = int(_val)
            if _ival < 0:
                raise ValueError(
                    f"current['{_metric}'] is negative ({_ival!r}); "
                    "token counts must be non-negative"
                )
    _nonneg_float_metrics = ("p95_latency_ms", "total_cost_usd")
    for _metric in _nonneg_float_metrics:
        _val = current.get(_metric)
        if _val is not None:
            _fval = float(_val)
            if math.isfinite(_fval) and _fval < 0.0:
                raise ValueError(
                    f"current['{_metric}'] is negative ({_fval!r}); "
                    "latency and cost metrics must be non-negative"
                )

    # Pass-rate gate: trip if pass rate drops more than allowed.
    cur_pass = _finite_number(current.get("pass_rate", 0.0), "current.pass_rate")
    drop = baseline.pass_rate - cur_pass
    if drop > tol.max_pass_rate_drop:
        trips.append(
            GateTripDetail(
                metric="pass_rate",
                baseline_value=baseline.pass_rate,
                current_value=cur_pass,
                threshold=tol.max_pass_rate_drop,
                direction="drop",
            )
        )

    # Token gate: trip if total tokens increased beyond allowed pct.
    cur_tokens = int(
        _finite_number(current.get("total_tokens_in", 0), "current.total_tokens_in")
    ) + int(_finite_number(current.get("total_tokens_out", 0), "current.total_tokens_out"))
    if baseline.total_tokens > 0:
        token_increase = (cur_tokens - baseline.total_tokens) / baseline.total_tokens
        if token_increase > tol.max_token_increase_pct:
            trips.append(
                GateTripDetail(
                    metric="total_tokens",
                    baseline_value=float(baseline.total_tokens),
                    current_value=float(cur_tokens),
                    threshold=tol.max_token_increase_pct,
                    direction="increase",
                )
            )
    else:
        skipped.append("total_tokens")

    # Latency gate.
    cur_lat = _finite_number(current.get("p95_latency_ms", 0.0), "current.p95_latency_ms")
    if baseline.p95_latency_ms > 0:
        lat_increase = (cur_lat - baseline.p95_latency_ms) / baseline.p95_latency_ms
        if lat_increase > tol.max_latency_increase_pct:
            trips.append(
                GateTripDetail(
                    metric="p95_latency_ms",
                    baseline_value=baseline.p95_latency_ms,
                    current_value=cur_lat,
                    threshold=tol.max_latency_increase_pct,
                    direction="increase",
                )
            )
    else:
        skipped.append("p95_latency_ms")

    # Cost gate.
    cur_cost = _finite_number(current.get("total_cost_usd", 0.0), "current.total_cost_usd")
    if baseline.total_cost_usd > 0:
        cost_increase = (cur_cost - baseline.total_cost_usd) / baseline.total_cost_usd
        if cost_increase > tol.max_cost_increase_pct:
            trips.append(
                GateTripDetail(
                    metric="total_cost_usd",
                    baseline_value=baseline.total_cost_usd,
                    current_value=cur_cost,
                    threshold=tol.max_cost_increase_pct,
                    direction="increase",
                )
            )
    else:
        skipped.append("total_cost_usd")

    return GateReport(ok=len(trips) == 0, trips=tuple(trips), skipped_zero_baseline=tuple(skipped))
