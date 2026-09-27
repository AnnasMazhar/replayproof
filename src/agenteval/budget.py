"""Regression gates that compare a current SuiteResult against a stored baseline.

A baseline is a persisted SuiteResult dict (JSON).  The gate trips if ANY
metric degrades beyond its configured tolerance.

Zero-baseline behaviour: when a baseline metric is exactly zero, the
percentage-increase gate for that metric cannot compute a meaningful ratio and
is skipped.  This is expected on the first run (no prior data).  The skipped
gates are recorded in GateReport.skipped_zero_baseline so callers can surface
them in CI output and avoid silent pass-throughs on corrupted baselines.
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


class Baseline:
    """A stored SuiteResult used as the reference point for gate comparison.

    Args:
        data: Dict produced by ``SuiteResult.to_dict()``.
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
        return float(self._data.get("pass_rate", 0.0))

    @property
    def total_tokens(self) -> int:
        """Baseline total tokens (in + out)."""
        return int(self._data.get("total_tokens_in", 0)) + int(
            self._data.get("total_tokens_out", 0)
        )

    @property
    def p95_latency_ms(self) -> float:
        """Baseline p95 latency in ms."""
        return float(self._data.get("p95_latency_ms", 0.0))

    @property
    def total_cost_usd(self) -> float:
        """Baseline total cost in USD."""
        return float(self._data.get("total_cost_usd", 0.0))


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

    Args:
        current: Dict produced by ``SuiteResult.to_dict()``.
        baseline: The stored Baseline to compare against.
        tolerances: Gate thresholds; defaults to Tolerances() if not given.

    Returns:
        GateReport with ok=True if all enforced gates pass.
    """
    tol = tolerances if tolerances is not None else Tolerances()
    trips: list[GateTripDetail] = []
    skipped: list[str] = []

    # Pass-rate gate: trip if pass rate drops more than allowed.
    cur_pass = float(current.get("pass_rate", 0.0))
    if not math.isfinite(cur_pass):
        raise ValueError(
            f"pass_rate must be a finite number, got {cur_pass!r}; "
            "a NaN or inf pass_rate indicates a corrupt or malformed result file"
        )
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
    cur_tokens = int(current.get("total_tokens_in", 0)) + int(current.get("total_tokens_out", 0))
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
    cur_lat = float(current.get("p95_latency_ms", 0.0))
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
    cur_cost = float(current.get("total_cost_usd", 0.0))
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
