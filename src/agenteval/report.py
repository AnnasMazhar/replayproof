"""Report generation: Markdown and self-contained HTML output.

The Markdown output is GitHub-flavoured and stable: no timestamps that
change between runs.  The HTML output is self-contained (inline CSS only,
no CDN, no JS dependencies).
"""

from __future__ import annotations

from agenteval.budget import GateReport
from agenteval.drift import DriftReport
from agenteval.scoring import SuiteResult


def to_markdown(
    suite: SuiteResult,
    drift: DriftReport | None = None,
    gate: GateReport | None = None,
) -> str:
    """Render a SuiteResult (and optional drift/gate) as GitHub-flavoured Markdown.

    The output is stable: re-running with the same inputs produces byte-identical
    output (no timestamps, no random ordering).

    Args:
        suite: The suite result to render.
        drift: Optional drift report to include.
        gate: Optional gate report to include.

    Returns:
        Markdown string.
    """
    lines: list[str] = []

    lines.append(f"# Evaluation Report: {suite.suite_name or 'unnamed'}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| ------ | ----- |")
    n = len(suite.case_results)
    n_passed = sum(1 for r in suite.case_results if r.passed)
    lines.append(f"| Cases | {n} |")
    lines.append(f"| Passed | {n_passed} |")
    lines.append(f"| Pass Rate | {suite.pass_rate_value:.1%} |")
    lines.append(f"| Wilson Lower Bound (95%) | {suite.wilson_lower_bound:.1%} |")
    lines.append(f"| Total Tokens In | {suite.total_tokens_in:,} |")
    lines.append(f"| Total Tokens Out | {suite.total_tokens_out:,} |")
    lines.append(f"| p50 Latency | {suite.p50_latency_ms:.1f} ms |")
    lines.append(f"| p95 Latency | {suite.p95_latency_ms:.1f} ms |")
    if suite.total_cost_usd > 0:
        lines.append(f"| Estimated Cost | ${suite.total_cost_usd:.6f} USD |")
    lines.append("")

    lines.append("## Per-Case Results")
    lines.append("")
    lines.append("| Case ID | Passed | Tokens In | Tokens Out | Latency ms |")
    lines.append("| ------- | ------ | --------- | ---------- | ---------- |")
    for r in suite.case_results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(
            f"| {r.case_id} | {status} | {r.tokens_in} | {r.tokens_out} | " f"{r.latency_ms:.1f} |"
        )
    lines.append("")

    if gate is not None:
        lines.append("## Gate Report")
        lines.append("")
        if gate.ok:
            lines.append("All gates passed.")
        else:
            lines.append("**Gate tripped.** The following metrics regressed:")
            lines.append("")
            lines.append("| Metric | Baseline | Current | Threshold | Direction |")
            lines.append("| ------ | -------- | ------- | --------- | --------- |")
            for t in gate.trips:
                lines.append(
                    f"| {t.metric} | {t.baseline_value:.4f} | "
                    f"{t.current_value:.4f} | {t.threshold:.4f} | {t.direction} |"
                )
        lines.append("")

    if drift is not None:
        lines.append("## Drift Report")
        lines.append("")
        lines.append(f"- Regressions: {len(drift.regressions)}")
        lines.append(f"- Fixes: {len(drift.fixes)}")
        lines.append(f"- Churn: {len(drift.churns)}")
        lines.append(f"- Stable pass: {len(drift.stable_passes)}")
        lines.append(f"- Stable fail: {len(drift.stable_fails)}")
        lines.append(f"- Token delta total: {drift.token_delta_total:+d}")
        lines.append(f"- Latency delta total: {drift.latency_delta_ms_total:+.1f} ms")
        lines.append("")
        if drift.regressions:
            lines.append("### Regressions (passing -> failing)")
            lines.append("")
            for cd in drift.regressions:
                lines.append(f"- `{cd.case_id}`: {cd.b_reason or '(no reason recorded)'}")
            lines.append("")
        if drift.fixes:
            lines.append("### Fixes (failing -> passing)")
            lines.append("")
            for cd in drift.fixes:
                lines.append(f"- `{cd.case_id}`")
            lines.append("")

    return "\n".join(lines)


def to_html(
    suite: SuiteResult,
    drift: DriftReport | None = None,
    gate: GateReport | None = None,
) -> str:
    """Render a SuiteResult as a self-contained HTML page.

    No CDN, no external assets, no JavaScript.  Inline CSS only.

    Args:
        suite: The suite result to render.
        drift: Optional drift report to include.
        gate: Optional gate report to include.

    Returns:
        Self-contained HTML string.
    """
    md = to_markdown(suite, drift=drift, gate=gate)
    # Simple but functional: wrap the markdown table rows in HTML tables.
    # This avoids a markdown parser dependency while still producing
    # readable HTML.
    rows_html = _md_tables_to_html(md)

    css = """
    body { font-family: sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; }
    h1, h2, h3 { color: #222; }
    table { border-collapse: collapse; width: 100%; margin: 1em 0; }
    th, td { border: 1px solid #ccc; padding: 0.4em 0.8em; text-align: left; }
    th { background: #f0f0f0; }
    tr:nth-child(even) { background: #fafafa; }
    .pass { color: #2a7a2a; font-weight: bold; }
    .fail { color: #c0392b; font-weight: bold; }
    pre { background: #f4f4f4; padding: 1em; overflow-x: auto; }
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Evaluation Report: {_esc(suite.suite_name or "unnamed")}</title>
<style>{css}</style>
</head>
<body>
{rows_html}
</body>
</html>"""
    return html


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _md_tables_to_html(md: str) -> str:
    """Convert a Markdown string with GFM tables to basic HTML.

    Non-table lines are wrapped in <p> or <h1-3> tags.
    """
    lines = md.split("\n")
    output: list[str] = []
    in_table = False
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal in_table, table_rows
        if not table_rows:
            return
        output.append("<table>")
        # First row is header; second row is separator (skip it).
        header = table_rows[0]
        output.append("<thead><tr>")
        for cell in header:
            output.append(f"  <th>{_esc(cell.strip())}</th>")
        output.append("</tr></thead>")
        output.append("<tbody>")
        for row in table_rows[2:]:
            output.append("<tr>")
            for cell in row:
                cell_text = cell.strip()
                if cell_text in ("PASS",):
                    cell_text = f'<span class="pass">{cell_text}</span>'
                elif cell_text in ("FAIL",):
                    cell_text = f'<span class="fail">{cell_text}</span>'
                else:
                    cell_text = _esc(cell_text)
                output.append(f"  <td>{cell_text}</td>")
            output.append("</tr>")
        output.append("</tbody></table>")
        in_table = False
        table_rows = []

    for line in lines:
        if line.startswith("| "):
            in_table = True
            cells = [c for c in line.split("|") if c != ""]
            table_rows.append(cells)
        else:
            if in_table:
                flush_table()
            if line.startswith("### "):
                output.append(f"<h3>{_esc(line[4:])}</h3>")
            elif line.startswith("## "):
                output.append(f"<h2>{_esc(line[3:])}</h2>")
            elif line.startswith("# "):
                output.append(f"<h1>{_esc(line[2:])}</h1>")
            elif line.startswith("- "):
                output.append(f"<li>{_esc(line[2:])}</li>")
            elif line.startswith("**") and line.endswith("**"):
                output.append(f"<p><strong>{_esc(line[2:-2])}</strong></p>")
            elif line.strip():
                output.append(f"<p>{_esc(line)}</p>")
            else:
                output.append("")

    if in_table:
        flush_table()

    return "\n".join(output)
