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

- test_readme_git_url_install_has_availability_note (TestREADMEInstallContract): catches
  a README where `pip install git+` appears without a caveat that the command requires
  the repo to be publicly accessible. Root cause of ADV2-3 (major, c2-p10): the primary
  install instruction failed for every user because the repo was private; anyone following
  the README hit `fatal: Authentication failed`. Fault injection: remove the
  "# Requires the repo to be publicly accessible:" comment line immediately preceding
  the `pip install git+` command => this test fails (no qualifying note found near the
  bare `pip install git+` line).

- test_mutation_report_has_real_data (TestMutationReportIntegrity): catches a mutation
  report JSON that records a failed run (rc != 0, killed/total/kill_rate = null) but is
  cited in EVIDENCE.md as containing real kill-rate numbers. Root cause of c5-p08
  finding: EVIDENCE.md section 9 claimed "Kill rate: 94.9%" from reports/mutation-c4.json
  but that file had rc=1 and null values from a runner failure. Fault injection: write
  a mutation report JSON with rc=1 and killed=null => this test fails because the most
  recent successful mutation report is expected to have rc=0 and numeric killed/total.

- test_adoption_install_uses_correct_package_name (TestAdoptionInstallContract): catches
  ADOPTION.md using the wrong PyPI package name 'agent-eval-harness>=0.1.0'. The PyPI
  slot is occupied by a different, unrelated package (Franck Ndzomga, 2026-02-09). Any
  stranger following the adoption guide would install the wrong package and then be
  confused when `import agenteval` fails. Root cause (c6-p09): the ADOPTION.md install
  step was written before the PyPI name collision was discovered in c2-p08. Fault
  injection: restore 'pip install agent-eval-harness' in ADOPTION.md => this test fails.

- test_readme_contract_yaml_contains_all_real_check_types (TestREADMEContractYAMLSync):
  catches the README 'Contract YAML' section being out of sync with the actual
  examples/contracts/research.yaml. Root cause (c7-p09): the README example was a
  simplified illustration missing the 'final_answer_not_empty' check added to the real
  contract file. Fault injection: add a new check type to research.yaml without updating
  the README => this test fails because the new type is absent from the README section.
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
        Injection tested: adding datetime.now() (renders as '2026-09-27 12:34:56.789')
        or datetime.utcnow().isoformat() (renders as '2026-09-27T12:34:56') both fail.
        """
        suite = _make_suite()
        md = to_markdown(suite)
        # Matches both ISO-T form (2026-09-27T12:34:56) and space form (2026-09-27 12:34:56)
        # and standalone dates (2026-09-27) and standalone times (12:34:56).
        date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
        time_pattern = re.compile(r"\d{2}:\d{2}:\d{2}")
        date_hits = date_pattern.findall(md)
        time_hits = time_pattern.findall(md)
        assert not date_hits, "Markdown report must not contain date strings. Found: " + str(
            date_hits
        )
        assert not time_hits, "Markdown report must not contain time strings. Found: " + str(
            time_hits
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


class TestREADMEInstallContract:
    """Fault: README's pip install git+ appears without an availability disclaimer.

    Root cause of ADV2-3 (major, c2-p10): the primary install instruction failed for
    every user because the repo was private. Anyone following the README hit
    fatal: Authentication failed for https://github.com/...

    This test enforces the invariant: every `pip install git+` line in README.md must
    have a qualifying note - on the immediately preceding line, within the same code
    block, or within 2 lines above - that indicates the command requires the repo to
    be publicly accessible.

    Fault injection: removing the `# Requires the repo to be publicly accessible:`
    comment line from README.md causes this test to fail, because the bare
    `pip install git+` line no longer has a qualifying note.
    """

    # Phrases that constitute an acceptable availability note.
    _NOTES = (
        "requires the repo to be publicly accessible",
        "requires the repo to be public",
        "only works when the repo is public",
        "only when the repo is public",
        "once the repo is public",
    )

    def _has_qualifying_note(self, lines: list, git_url_lineno: int) -> bool:
        """Return True if any of the 3 lines preceding git_url_lineno contain a note."""
        window = lines[max(0, git_url_lineno - 3) : git_url_lineno]
        combined = " ".join(line.lower() for line in window)
        return any(note in combined for note in self._NOTES)

    def test_readme_git_url_install_has_availability_note(self) -> None:
        """Every pip install git+ line in README.md must be preceded by a note.

        Fault injection: remove the qualifying comment above the pip install git+ line
        => the window above the command no longer contains any qualifying phrase
        => this assertion fails.
        """
        import os
        import pathlib

        # Walk up from this file's directory until we find README.md.
        # This handles both the normal layout (tests/test_report.py → repo root)
        # and the mutmut layout (mutants/tests/test_report.py → mutants/ → repo root).
        env_root = os.environ.get("REPO_ROOT")
        if env_root:
            readme_path = pathlib.Path(env_root) / "README.md"
        else:
            candidate = pathlib.Path(__file__).resolve().parent
            readme_path = candidate / "README.md"
            while not readme_path.exists() and candidate.parent != candidate:
                candidate = candidate.parent
                readme_path = candidate / "README.md"
        assert (
            readme_path.exists()
        ), f"README.md not found (searched up from {pathlib.Path(__file__).resolve()})"
        lines = readme_path.read_text(encoding="utf-8").splitlines()

        violations: list = []
        for i, line in enumerate(lines):
            if "pip install git+" in line:
                if not self._has_qualifying_note(lines, i):
                    violations.append(i + 1)  # 1-indexed line number

        assert not violations, (
            "README.md has `pip install git+` on line(s) "
            + str(violations)
            + " without a preceding note that the command requires the repo to be publicly "
            "accessible. Add a comment like '# Requires the repo to be publicly accessible:' "
            "on the line immediately before each `pip install git+` command, or reorder the "
            "Install section so the source-install path (git clone + pip install .) comes first."
        )


class TestMutationReportIntegrity:
    """Fault: a mutation report JSON has rc != 0 and killed/total = null (runner failure),
    but EVIDENCE.md cites it as containing real kill-rate numbers.

    Root cause (c5-p08): EVIDENCE.md section 9 claimed "Kill rate: 94.9%" from
    reports/mutation-c4.json, but that file recorded rc=1 and null values because
    the mutmut subprocess failed (README path issue, fixed in c5-p04 via conftest.py).
    The c5-p05 EVIDENCE refresh wrote the historical 94.8% number without reading
    the committed JSON, so the claim and the file were out of sync.

    This test enforces the invariant: the most recent successful mutation report
    (reports/mutation-c5.json) must exist, have rc=0, and contain integer killed/total
    and a float kill_rate above the 70% target. Any run that writes null values or rc!=0
    fails this test.

    Fault injection: write a mutation report with rc=1 and killed=null (as mutation-c4.json
    does) and point this test at it => the assertions on rc==0 and isinstance(killed, int)
    would fail, catching the fabricated evidence immediately.
    """

    def _find_repo_root(self) -> str:
        import pathlib as _pathlib

        env_root = os.environ.get("REPO_ROOT")
        if env_root:
            return env_root
        candidate = _pathlib.Path(__file__).resolve().parent
        while not (candidate / "reports").is_dir() and candidate.parent != candidate:
            candidate = candidate.parent
        return str(candidate)

    def test_mutation_report_has_real_data(self) -> None:
        """reports/mutation-c5.json must exist, have rc=0, and contain numeric kill data.

        Fault injection: replace reports/mutation-c5.json with {"rc": 1, "killed": null,
        "total": null, "kill_rate": null} (as mutation-c4.json looks) => this test fails
        on rc == 0 assertion and isinstance(killed, int) assertion.
        """
        import json
        import pathlib

        repo_root = pathlib.Path(self._find_repo_root())
        report_path = repo_root / "reports" / "mutation-c5.json"
        assert report_path.exists(), (
            f"reports/mutation-c5.json not found at {report_path}. "
            "The mutation pass must produce a report with real (non-null) data."
        )
        data = json.loads(report_path.read_text(encoding="utf-8"))

        assert data.get("rc") == 0, (
            f"reports/mutation-c5.json has rc={data.get('rc')} (expected 0). "
            "A non-zero rc means the mutation runner failed; null kill data cannot "
            "be cited in EVIDENCE.md as a real mutation score."
        )
        killed = data.get("killed")
        total = data.get("total")
        kill_rate = data.get("kill_rate")
        assert isinstance(killed, int) and killed > 0, (
            f"reports/mutation-c5.json killed={killed!r} is not a positive integer. "
            "The file records a runner failure, not a real mutation run."
        )
        assert (
            isinstance(total, int) and total > 0
        ), f"reports/mutation-c5.json total={total!r} is not a positive integer."
        assert isinstance(kill_rate, float) and kill_rate > 0.70, (
            f"reports/mutation-c5.json kill_rate={kill_rate!r} is below the 70% target "
            "or not a float. Expected >=0.70."
        )
        # Consistency check: kill_rate must match killed/total within 1%
        expected_rate = killed / total
        assert abs(kill_rate - expected_rate) < 0.01, (
            f"kill_rate={kill_rate:.4f} inconsistent with killed/total={expected_rate:.4f}. "
            "The JSON may have been hand-edited rather than generated from a real run."
        )


class TestAdoptionInstallContract:
    """Fault: ADOPTION.md uses the wrong PyPI package name 'agent-eval-harness>=0.1.0'.

    Root cause (c6-p09-improve-2): ADOPTION.md was written before the PyPI name
    collision was discovered in c2-p08. The PyPI slot 'agent-eval-harness' is occupied
    by a different, unrelated package (Franck Ndzomga, 2026-02-09). Any engineer
    following the adoption guide would install the wrong package and then see
    'ImportError: No module named agenteval' with no clear explanation.

    The correct install is from source (git clone + pip install .) or from the git URL
    once the repo is public. The README already shows this correctly (fixed in c2-p08).

    Fault injection: restore 'pip install agent-eval-harness' in docs/ADOPTION.md =>
    this test fails because the bad package name is detected without a PyPI disclaimer.
    """

    _BAD_NAMES = (
        "pip install agent-eval-harness",
        "pip install 'agent-eval-harness",
        'pip install "agent-eval-harness',
        "uv pip install agent-eval-harness",
        "uv pip install 'agent-eval-harness",
    )

    def _find_repo_root(self) -> str:
        import os

        env_root = os.environ.get("REPO_ROOT")
        if env_root:
            return env_root
        import pathlib

        candidate = pathlib.Path(__file__).resolve().parent
        while not (candidate / "docs").is_dir() and candidate.parent != candidate:
            candidate = candidate.parent
        return str(candidate)

    def test_adoption_install_uses_correct_package_name(self) -> None:
        """ADOPTION.md must not install from the occupied PyPI name 'agent-eval-harness'.

        The PyPI slot 'agent-eval-harness' is occupied by a different package. Any
        line containing 'pip install agent-eval-harness' in ADOPTION.md (without a
        clear disclaimer that this installs the wrong thing) will mislead engineers.

        Fault injection: add 'pip install agent-eval-harness>=0.1.0' to ADOPTION.md
        without a disclaimer => assertion fails because the bad name is detected.
        """
        import pathlib

        adoption_path = pathlib.Path(self._find_repo_root()) / "docs" / "ADOPTION.md"
        assert adoption_path.exists(), (
            f"docs/ADOPTION.md not found at {adoption_path}. " "The adoption guide must exist."
        )
        lines = adoption_path.read_text(encoding="utf-8").splitlines()

        violations: list[int] = []
        for i, line in enumerate(lines):
            lower = line.lower()
            if any(bad in lower for bad in self._BAD_NAMES):
                # Allow the line if it is inside a note/warning explaining the collision.
                # Check whether the line itself or the 3 preceding lines contain a disclaimer.
                window = lines[max(0, i - 3) : i + 1]
                combined = " ".join(ln.lower() for ln in window)
                disclaimer_phrases = (
                    "different, unrelated package",
                    "different package",
                    "occupied by",
                    "wrong package",
                    "installs the wrong",
                )
                if not any(p in combined for p in disclaimer_phrases):
                    violations.append(i + 1)  # 1-indexed

        assert not violations, (
            "docs/ADOPTION.md references the occupied PyPI name 'agent-eval-harness' "
            "on line(s) " + str(violations) + " without a disclaimer. "
            "The PyPI name 'agent-eval-harness' is occupied by a different, unrelated "
            "package (Franck Ndzomga, 2026-02-09). Use source install instead: "
            "'git clone https://github.com/AnnasMazhar/replayproof && pip install -e .'."
        )


class TestREADMEContractYAMLSync:
    """Fault: README 'Contract YAML' section shows an example that is missing checks
    present in the actual examples/contracts/research.yaml.

    Root cause (c7-p09): The README example was a simplified illustration. When the
    real research.yaml gained the 'final_answer_not_empty' check, the README example
    was not updated. A skeptical reviewer who copies the README example and compares it
    to the file will see the discrepancy immediately.

    This test verifies that every 'type:' value that appears in the real
    examples/contracts/research.yaml also appears in the README 'Contract YAML' section.

    Fault injection: add a new check type to examples/contracts/research.yaml without
    updating the README example => this test fails because the new type is not found in
    the README code block.
    """

    def _find_repo_root(self) -> str:
        import os
        import pathlib

        env_root = os.environ.get("REPO_ROOT")
        if env_root:
            return env_root
        candidate = pathlib.Path(__file__).resolve().parent
        while not (candidate / "docs").is_dir() and candidate.parent != candidate:
            candidate = candidate.parent
        return str(candidate)

    def test_readme_contract_yaml_contains_all_real_check_types(self) -> None:
        """README Contract YAML section must include all check types from research.yaml.

        The README shows a 'Contract YAML' code block as an example. If the real
        examples/contracts/research.yaml contains a check type that the README example
        omits, a reviewer copying from the README will produce a weaker contract than
        the committed example. The discrepancy also signals that the README is out of sync
        with the code.

        Fault injection: remove 'final_answer_not_empty' from the README Contract YAML
        section => this test fails because 'final_answer_not_empty' is found in
        research.yaml but not in the README Contract YAML block.
        """
        import pathlib
        import re

        repo_root = pathlib.Path(self._find_repo_root())
        readme = (repo_root / "README.md").read_text(encoding="utf-8")
        research_yaml = (repo_root / "examples" / "contracts" / "research.yaml").read_text(
            encoding="utf-8"
        )

        # Extract all 'type: <value>' from research.yaml
        real_types = set(re.findall(r"^\s*type:\s*(\S+)", research_yaml, re.MULTILINE))

        # Extract the README's 'Contract YAML' section: the code block between
        # '## Contract YAML' and the next '## ' header.
        contract_section_match = re.search(
            r"## Contract YAML\n(.*?)(?=\n## |\Z)", readme, re.DOTALL
        )
        assert (
            contract_section_match
        ), "README.md must contain a '## Contract YAML' section showing the YAML format."
        contract_section = contract_section_match.group(1)

        # Find all 'type: <value>' in that section
        readme_types = set(re.findall(r"type:\s*(\S+)", contract_section))

        missing = real_types - readme_types
        assert not missing, (
            f"README 'Contract YAML' section is missing check type(s) that appear in "
            f"examples/contracts/research.yaml: {sorted(missing)}. "
            "Update the README example to include all check types from the real contract. "
            "This prevents README-code drift that misleads engineers who copy the example."
        )
