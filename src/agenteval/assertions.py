"""Declarative assertion language for agent run contracts.

Each check has a stable id, human-readable description, and severity.
A Contract is a list of checks loadable from YAML.

PII_PATTERNS ships a minimal set of patterns for common sensitive data;
callers can extend or replace it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import jsonschema
import yaml

from agenteval.transcript import Run

# Default PII patterns (pattern name -> compiled regex).
# Source: adapted from EACL 2026 R&R detector suite; see docs/RESEARCH.md.
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "us_phone": re.compile(r"\b(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"),
    "us_ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
}


@dataclass(frozen=True)
class CheckResult:
    """Result of a single assertion check against one Run."""

    check_id: str
    passed: bool
    severity: str  # "error" or "warn"
    message: str


@dataclass(frozen=True)
class CheckResults:
    """Aggregate results of evaluating a Contract against a Run."""

    results: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        """True if no error-severity check failed."""
        return all(r.passed or r.severity != "error" for r in self.results)

    @property
    def errors(self) -> list[CheckResult]:
        """All failed error-severity checks."""
        return [r for r in self.results if not r.passed and r.severity == "error"]

    @property
    def warnings(self) -> list[CheckResult]:
        """All failed warn-severity checks."""
        return [r for r in self.results if not r.passed and r.severity == "warn"]


class Check:
    """Base class for all assertion checks."""

    id: str = ""
    description: str = ""
    severity: str = "error"

    def evaluate(self, run: Run) -> CheckResult:  # pragma: no cover
        raise NotImplementedError


@dataclass
class ToolSequenceCheck(Check):
    """Assert that required tools appear (as a subsequence or subset).

    Fault detected: agent skips a required tool call or inverts the mandated order.

    Args:
        expected: Ordered list of tool names that must appear.
        ordered: If True (default), the names must appear as a subsequence in
                 the recorded order.  If False, presence only is checked.
    """

    id: str = "tool_sequence"
    description: str = "Required tool call sequence"
    severity: str = "error"
    expected: list[str] = field(default_factory=list)
    ordered: bool = True

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: wrong tool order or missing required call."""
        actual_names = [tc.name for tc in run.all_tool_calls()]
        if self.ordered:
            # Subsequence check: iterate expected in order, consuming actual.
            idx = 0
            for name in self.expected:
                while idx < len(actual_names) and actual_names[idx] != name:
                    idx += 1
                if idx >= len(actual_names):
                    return CheckResult(
                        check_id=self.id,
                        passed=False,
                        severity=self.severity,
                        message=(
                            f"Tool '{name}' not found in required sequence position. "
                            f"Actual tool calls: {actual_names}"
                        ),
                    )
                idx += 1
        else:
            missing = [n for n in self.expected if n not in actual_names]
            if missing:
                return CheckResult(
                    check_id=self.id,
                    passed=False,
                    severity=self.severity,
                    message=f"Required tools not called: {missing}. Actual: {actual_names}",
                )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


@dataclass
class RequiredToolsCheck(Check):
    """Assert that all named tools were called at least once.

    Fault detected: agent omits a tool that the contract mandates.
    """

    id: str = "required_tools"
    description: str = "All required tools must be called"
    severity: str = "error"
    names: list[str] = field(default_factory=list)

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: required tool not present in run."""
        actual = {tc.name for tc in run.all_tool_calls()}
        missing = sorted(n for n in self.names if n not in actual)
        if missing:
            return CheckResult(
                check_id=self.id,
                passed=False,
                severity=self.severity,
                message=f"Required tools not called: {missing}",
            )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


@dataclass
class ForbiddenToolsCheck(Check):
    """Assert that no named tools were called.

    Fault detected: agent calls a tool the contract prohibits.
    """

    id: str = "forbidden_tools"
    description: str = "Forbidden tools must not be called"
    severity: str = "error"
    names: list[str] = field(default_factory=list)

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: forbidden tool present in run."""
        actual = {tc.name for tc in run.all_tool_calls()}
        called = sorted(n for n in self.names if n in actual)
        if called:
            return CheckResult(
                check_id=self.id,
                passed=False,
                severity=self.severity,
                message=f"Forbidden tools were called: {called}",
            )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


@dataclass
class ArgSchemaCheck(Check):
    """Assert that a named tool's args conform to a JSON Schema.

    Fault detected: agent passes malformed or missing args to a tool.
    """

    id: str = "arg_schema"
    description: str = "Tool arguments must match JSON schema"
    severity: str = "error"
    tool: str = ""
    schema: dict[str, Any] = field(default_factory=dict)

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: args fail JSON Schema validation or contain non-JSON values."""
        import json as _json

        for tc in run.all_tool_calls():
            if tc.name != self.tool:
                continue
            # Pre-validate that args are JSON-serialisable (rejects inf, NaN, etc.).
            # JSON has no Infinity or NaN; passing them to a downstream tool that
            # serialises args would produce invalid JSON.
            try:
                _json.dumps(tc.args, allow_nan=False)
            except (TypeError, ValueError) as exc:
                return CheckResult(
                    check_id=self.id,
                    passed=False,
                    severity=self.severity,
                    message=f"Tool '{self.tool}' args contain non-JSON-serialisable values: {exc}",
                )
            try:
                jsonschema.validate(instance=tc.args, schema=self.schema)
            except jsonschema.ValidationError as exc:
                return CheckResult(
                    check_id=self.id,
                    passed=False,
                    severity=self.severity,
                    message=f"Tool '{self.tool}' arg validation failed: {exc.message}",
                )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


@dataclass
class MaxToolCallsCheck(Check):
    """Assert that the total number of tool calls does not exceed a limit.

    Fault detected: agent enters a loop or exceeds the allowed call budget.
    """

    id: str = "max_tool_calls"
    description: str = "Total tool calls must not exceed maximum"
    severity: str = "error"
    n: int = 0

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: too many tool calls."""
        count = len(run.all_tool_calls())
        if count > self.n:
            return CheckResult(
                check_id=self.id,
                passed=False,
                severity=self.severity,
                message=f"Tool call count {count} exceeds limit {self.n}",
            )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


@dataclass
class MaxTokensCheck(Check):
    """Assert that total tokens consumed do not exceed a limit.

    Fault detected: agent uses more tokens than the budget allows.
    """

    id: str = "max_tokens"
    description: str = "Total tokens must not exceed maximum"
    severity: str = "warn"
    n: int = 0

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: token budget exceeded."""
        total = run.total_tokens_in + run.total_tokens_out
        if total > self.n:
            return CheckResult(
                check_id=self.id,
                passed=False,
                severity=self.severity,
                message=f"Token count {total} exceeds limit {self.n}",
            )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


@dataclass
class MaxLatencyCheck(Check):
    """Assert that total latency does not exceed a limit in milliseconds.

    Fault detected: agent takes too long, violating a SLA.
    """

    id: str = "max_latency_ms"
    description: str = "Total latency must not exceed maximum"
    severity: str = "warn"
    n: float = 0.0

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: latency SLA breached."""
        if run.total_latency_ms > self.n:
            return CheckResult(
                check_id=self.id,
                passed=False,
                severity=self.severity,
                message=(f"Latency {run.total_latency_ms:.1f}ms exceeds " f"limit {self.n:.1f}ms"),
            )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


@dataclass
class NoPatternCheck(Check):
    """Assert that a field does not match a regex (e.g. PII or secret leakage).

    Fault detected: sensitive data (phone number, email, secret) present in output.

    Args:
        field_name: One of 'final_content', 'tool_args', 'all_content'.
        regex: Regular expression that must not match.
    """

    id: str = "no_pattern"
    description: str = "Field must not match forbidden regex"
    severity: str = "error"
    field_name: str = "final_content"
    regex: str = ""

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: forbidden pattern found in output."""
        pattern = re.compile(self.regex)
        targets: list[str] = []

        if self.field_name == "final_content":
            targets = [run.final_content()]
        elif self.field_name == "tool_args":
            import json as _json

            targets = [_json.dumps(tc.args) for tc in run.all_tool_calls()]
        elif self.field_name == "all_content":
            targets = [t.content for t in run.turns]
        else:
            targets = [run.final_content()]

        for text in targets:
            if pattern.search(text):
                return CheckResult(
                    check_id=self.id,
                    passed=False,
                    severity=self.severity,
                    message=(
                        f"Forbidden pattern '{self.regex}' found in field '{self.field_name}'"
                    ),
                )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


@dataclass
class FinalAnswerMatchesCheck(Check):
    """Assert that the final assistant response matches a regex.

    Fault detected: agent produces an answer in the wrong format.
    """

    id: str = "final_answer_matches"
    description: str = "Final answer must match regex"
    severity: str = "error"
    regex: str = ""

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: final answer does not match required pattern."""
        content = run.final_content()
        if not re.search(self.regex, content):
            return CheckResult(
                check_id=self.id,
                passed=False,
                severity=self.severity,
                message=(
                    f"Final answer does not match pattern '{self.regex}'. "
                    f"Got: {content[:120]!r}"
                ),
            )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


@dataclass
class FinalAnswerNotEmptyCheck(Check):
    """Assert that the agent produced a non-empty final answer.

    Fault detected: agent returns empty string (silent failure).
    """

    id: str = "final_answer_not_empty"
    description: str = "Final answer must not be empty"
    severity: str = "error"

    def evaluate(self, run: Run) -> CheckResult:
        """Fault detected: empty final answer."""
        if not run.final_content().strip():
            return CheckResult(
                check_id=self.id,
                passed=False,
                severity=self.severity,
                message="Final answer is empty",
            )
        return CheckResult(check_id=self.id, passed=True, severity=self.severity, message="ok")


# Registry mapping YAML check type strings to classes.
_CHECK_REGISTRY: dict[str, type] = {
    "tool_sequence": ToolSequenceCheck,
    "required_tools": RequiredToolsCheck,
    "forbidden_tools": ForbiddenToolsCheck,
    "arg_schema": ArgSchemaCheck,
    "max_tool_calls": MaxToolCallsCheck,
    "max_tokens": MaxTokensCheck,
    "max_latency_ms": MaxLatencyCheck,
    "no_pattern": NoPatternCheck,
    "final_answer_matches": FinalAnswerMatchesCheck,
    "final_answer_not_empty": FinalAnswerNotEmptyCheck,
}


def _build_check(spec: dict[str, Any]) -> Check:
    """Instantiate a Check from a YAML-deserialized dict."""
    check_type = spec.get("type", "")
    cls = _CHECK_REGISTRY.get(check_type)
    if cls is None:
        raise ValueError(f"Unknown check type: {check_type!r}")
    kwargs = {k: v for k, v in spec.items() if k != "type"}
    return cls(**kwargs)  # type: ignore[return-value]


class Contract:
    """An ordered list of checks, loadable from YAML.

    Args:
        checks: List of Check instances.
        name: Human-readable contract name.
    """

    def __init__(self, checks: list[Check], name: str = "") -> None:
        self.checks = checks
        self.name = name

    def evaluate(self, run: Run) -> CheckResults:
        """Evaluate all checks against *run* and return aggregate results.

        Args:
            run: The Run to evaluate.

        Returns:
            CheckResults with one CheckResult per check.
        """
        return CheckResults(
            results=tuple(
                sorted(
                    (check.evaluate(run) for check in self.checks),
                    key=lambda r: r.check_id,
                )
            )
        )

    @classmethod
    def from_yaml(cls, text: str) -> Contract:
        """Parse a YAML contract definition.

        Expected top-level keys: ``name`` (optional), ``checks`` (list).

        Args:
            text: YAML string.

        Returns:
            Contract instance.
        """
        data = yaml.safe_load(text)
        name = data.get("name", "")
        raw_checks = data.get("checks", [])
        checks = [_build_check(spec) for spec in raw_checks]
        return cls(checks=checks, name=name)

    @classmethod
    def from_yaml_file(cls, path: str) -> Contract:
        """Load a YAML contract from a file path.

        Args:
            path: Filesystem path to the YAML file.

        Returns:
            Contract instance.
        """
        with open(path, encoding="utf-8") as fh:
            return cls.from_yaml(fh.read())

    def to_yaml(self) -> str:
        """Serialise back to a YAML string (round-trip).

        Returns:
            YAML string representation of this contract.
        """
        data: dict[str, Any] = {"name": self.name, "checks": []}
        for check in self.checks:
            spec: dict[str, Any] = {"type": check.id}
            for attr_name in vars(check):
                if attr_name not in ("id", "description"):
                    spec[attr_name] = getattr(check, attr_name)
            data["checks"].append(spec)
        return yaml.dump(data, default_flow_style=False, sort_keys=True)
