"""CI check: fail if any paper in docs/PAPER-TRACEABILITY.md has status=UNTRACED.

Usage:
    python scripts/check_research_traceability.py

Exit codes:
    0  All cited papers are traced (have an implementation symbol and a test).
    1  One or more papers are UNTRACED.  The untraced rows are printed.

The check is intentionally simple: it scans for table rows in the markdown
file that contain the literal string 'UNTRACED' (case-insensitive).  A row
is compliant when the final column reads 'TRACED' or some other non-UNTRACED
value.  A paper we cannot implement or test must be removed from the table
rather than left with an UNTRACED status.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TRACEABILITY_FILE = Path(__file__).parent.parent / "docs" / "PAPER-TRACEABILITY.md"


def main() -> int:
    """Return 0 if all papers are traced, 1 if any are untraced."""
    if not TRACEABILITY_FILE.exists():
        print(
            f"error: {TRACEABILITY_FILE} not found — PAPER-TRACEABILITY.md is required",
            file=sys.stderr,
        )
        return 1

    text = TRACEABILITY_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Collect markdown table rows (start with |, contain multiple | separators).
    table_row_re = re.compile(r"^\|.*\|.*\|")
    # Skip header and separator rows (rows with only |, -, and spaces).
    separator_re = re.compile(r"^\|[-| :]+\|$")

    untraced: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        if not table_row_re.match(line):
            continue
        if separator_re.match(line.replace(" ", "")):
            continue
        if "UNTRACED" in line.upper():
            untraced.append((lineno, line.strip()))

    if untraced:
        print(
            f"FAIL: {len(untraced)} untraced paper(s) in {TRACEABILITY_FILE}:",
            file=sys.stderr,
        )
        for lineno, row in untraced:
            # Print only the first column (paper title) to keep output readable.
            cols = [c.strip() for c in row.split("|") if c.strip()]
            paper = cols[1] if len(cols) > 1 else row
            print(f"  line {lineno}: {paper}", file=sys.stderr)
        print(
            "\nA paper with UNTRACED status must either be implemented+tested or removed.",
            file=sys.stderr,
        )
        return 1

    n_traced = sum(
        1
        for line in lines
        if table_row_re.match(line)
        and not separator_re.match(line.replace(" ", ""))
        and "|" in line
        and "TRACED" in line.upper()
    )
    print(f"OK: all {n_traced} cited papers are traced in {TRACEABILITY_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
