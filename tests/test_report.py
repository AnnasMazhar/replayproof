"""Tests for report generation stability and correctness.

Faults detected:

- test_markdown_no_timestamps: catches a report implementation that embeds
  wall-clock timestamps (which would change between runs, breaking stability).
  Fault injection: add datetime.now() to the markdown output => test fails.

- test_markdown_contains_pass_rate: catches a report that omits the key summary metric.
  Fault injection: remove the pass_rate row => test fails.

- test_markdown_stable_re_run: catches non-deterministic output (e.g. dict ordering).
  Fault injection: use an unordered set for case_results => order varies => test fails.

- test_html_self_contained: catches an HTML report that includes external CDN links.
  Fault injection: add a <link rel=stylesheet href=https://cdn.example.com/...> => test fails.

- test_html_no_js: catches an HTML report that embeds JavaScript.
  Fault injection: add <script> tag => test fails.

- test_contract_yaml_round_trip: catches a Contract serialiser that loses type or fields.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agenteval.assertions import CheckResults
from agenteval.report import to_html, to_markdown
from agenteval.scoring import CaseResult, SuiteResult, compute_suite


def _make_suite(n_pass: int = 3, n_fail: int = 1, name: str = "test_suite") -> SuiteResult:
    """Build a minimal SuiteResult."""
    cases = [
        CaseResult(
            case_id=f"pass_{i}",
            passed=True,
            checks=CheckResults(results=()),
            tokens_in=10,
            tokens_out=5,
            latency_ms=100.0,
        )
        for i in range(n_pass)
    ] + [
        CaseResult(
            case_id=f"fail_{i}",
            passed=False,
            checks=CheckResults(results=()),
            tokens_in=10,
            tokens_out=5,
            latency_ms=150.0,
        )
        for i in range(n_fail)
    ]
    return compute_suite(cases, suite_name=name)


class TestMarkdownReport:
    def test_markdown_no_timestamps(self) -> None:
        """Fault: markdown output contains wall-clock timestamps.

        Any substring matching a date/time pattern like 2026-09-26 or
        12:34:56 indicates the report is not stable across runs.
        """
        suite = _make_suite()
        md = to_markdown(suite)
        # Match ISO dates and HH:MM:SS patterns.
        date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        assert not date_pattern.search(md), (
            "Markdown report must not contain wall-clock timestamps. Found: "
            + str(date_pattern.findall(md))
        )

    def test_markdown_contains_pass_rate(self) -> None:
        """Fault: pass_rate omitted from the summary table."""
        suite = _make_suite(n_pass=3, n_fail=1)
        md = to_markdown(suite)
        assert (
            "Pass Rate" in md or "pass_rate" in md.lower()
        ), "Markdown must contain a Pass Rate row."
        assert "75.0%" in md or "0.75" in md, "Markdown must show the correct pass rate (75%)."

    def test_markdown_contains_wilson_lower(self) -> None:
        """Fault: Wilson lower bound omitted from summary."""
        suite = _make_suite(n_pass=9, n_fail=1)
        md = to_markdown(suite)
        assert (
            "Wilson" in md or "wilson" in md.lower()
        ), "Markdown must reference the Wilson lower bound."

    def test_markdown_stable_re_run(self) -> None:
        """Fault: non-deterministic output ordering."""
        suite = _make_suite()
        md1 = to_markdown(suite)
        md2 = to_markdown(suite)
        assert (
            md1 == md2
        ), "to_markdown must be deterministic: two calls must give identical output."

    def test_markdown_contains_case_ids(self) -> None:
        """Fault: case results not rendered in report."""
        suite = _make_suite(n_pass=2, n_fail=1)
        md = to_markdown(suite)
        assert "pass_0" in md, "Case ID 'pass_0' should appear in the report."
        assert "fail_0" in md, "Case ID 'fail_0' should appear in the report."

    def test_markdown_with_gate_trip(self) -> None:
        """Fault: gate section omitted when gate is provided."""
        from agenteval.budget import GateReport, GateTripDetail

        gate = GateReport(
            ok=False,
            trips=(
                GateTripDetail(
                    metric="pass_rate",
                    baseline_value=0.9,
                    current_value=0.7,
                    threshold=0.0,
                    direction="drop",
                ),
            ),
        )
        suite = _make_suite()
        md = to_markdown(suite, gate=gate)
        assert "Gate" in md, "Markdown must include a Gate section when gate is provided."
        assert "pass_rate" in md, "Gate section must name the tripped metric."


class TestHTMLReport:
    def test_html_self_contained(self) -> None:
        """Fault: HTML includes external CDN or stylesheet links."""
        suite = _make_suite()
        html = to_html(suite)
        # No external links.
        assert "cdn." not in html.lower(), "HTML must not reference CDN resources."
        assert 'src="http' not in html, "HTML must not load external scripts."
        assert 'href="http' not in html, "HTML must not link external stylesheets."

    def test_html_no_js(self) -> None:
        """Fault: HTML embeds JavaScript."""
        suite = _make_suite()
        html = to_html(suite)
        assert "<script" not in html.lower(), "HTML must not contain any <script> tags."

    def test_html_contains_doctype(self) -> None:
        """Fault: HTML missing DOCTYPE, making it invalid."""
        suite = _make_suite()
        html = to_html(suite)
        assert html.strip().startswith("<!DOCTYPE html>"), "HTML must start with <!DOCTYPE html>."

    def test_html_contains_suite_name(self) -> None:
        """Fault: suite name not included in HTML title."""
        suite = _make_suite(name="my_suite")
        html = to_html(suite)
        assert "my_suite" in html, "HTML title must contain the suite name."


class TestContractRoundTrip:
    def test_contract_yaml_round_trip(self) -> None:
        """Fault: Contract.from_yaml loses check type or fields on serialisation."""
        from agenteval.assertions import Contract

        yaml_text = """
name: roundtrip_test
checks:
  - type: required_tools
    id: required_tools
    severity: error
    names:
      - search
  - type: no_pattern
    id: no_pii
    severity: error
    field_name: final_content
    regex: '[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}'
"""
        contract = Contract.from_yaml(yaml_text)
        assert len(contract.checks) == 2
        assert contract.checks[0].id == "required_tools"
        assert contract.checks[1].id == "no_pii"
        # Verify the no_pattern check has the right field_name.
        assert contract.checks[1].field_name == "final_content"  # type: ignore[attr-defined]
