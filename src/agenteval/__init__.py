"""agenteval — deterministic, offline-replayable regression testing for LLM agents."""

__version__ = "0.1.0"

from agenteval.assertions import Contract
from agenteval.budget import Baseline, GateReport, compare
from agenteval.drift import DriftReport, drift
from agenteval.record import Recorder
from agenteval.replay import ReplayMismatch, replay
from agenteval.report import to_html, to_markdown
from agenteval.scoring import CaseResult, SuiteResult, pass_rate, wilson_lower
from agenteval.transcript import Run, ToolCall, Turn

__all__ = [
    "__version__",
    "Run",
    "Turn",
    "ToolCall",
    "Recorder",
    "replay",
    "ReplayMismatch",
    "Contract",
    "SuiteResult",
    "CaseResult",
    "pass_rate",
    "wilson_lower",
    "Baseline",
    "compare",
    "GateReport",
    "drift",
    "DriftReport",
    "to_markdown",
    "to_html",
]
