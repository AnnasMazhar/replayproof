"""Guardrails over the committed REAL recordings.

These are the artefacts the whole real-world proof rests on, so they get the
same treatment as code:

- every JSONL line must parse as a schema-valid Run (a corrupted or
  hand-edited recording silently breaks replay);
- no host paths or internal system names may leak into committed recordings
  (CI enforces redaction; this test is the enforcement);
- the recordings must actually be real-model runs: non-zero provider token
  accounting on assistant turns.
"""

from __future__ import annotations

import glob
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agenteval.transcript import Run

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
RECORDINGS = sorted(glob.glob(os.path.join(REPO_ROOT, "examples", "recordings", "real_*.jsonl")))

FORBIDDEN_PATTERNS = [
    (re.compile(r"/home/[A-Za-z0-9._-]+"), "host home path"),
    (re.compile(r"(?<![A-Za-z])openclaw(?![A-Za-z])"), "internal system name"),
    (re.compile(r"thinkstation", re.IGNORECASE), "internal host model"),
]


def _read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


def test_real_recordings_exist() -> None:
    """Fault detected: real recordings removed or never committed."""
    assert (
        len(RECORDINGS) >= 3
    ), f"expected at least 3 real recordings, found {len(RECORDINGS)}: {RECORDINGS}"


@pytest.mark.parametrize("path", RECORDINGS)
def test_recording_lines_parse_as_runs(path: str) -> None:
    """Fault detected: a committed recording that the schema cannot load."""
    lines = _read_lines(path)
    assert lines, f"{path} is empty"
    for i, line in enumerate(lines, start=1):
        run = Run.from_jsonl(line)  # raises KeyError/ValueError on schema drift
        assert run.name, f"{os.path.basename(path)} line {i} has no run name"
        assert run.turns, f"{os.path.basename(path)} line {i} has no turns"
        assert run.schema_version == "1"


@pytest.mark.parametrize("path", RECORDINGS)
def test_recording_is_redacted(path: str) -> None:
    """Fault detected: host paths or internal names committed to a recording."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for pattern, label in FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        assert match is None, f"{os.path.basename(path)} contains {label}: {match.group(0)!r}"


@pytest.mark.parametrize("path", RECORDINGS)
def test_recording_has_provider_token_accounting(path: str) -> None:
    """Fault detected: a 'real' recording with no token counts (synthetic fill).

    Every real recording must show non-zero tokens somewhere — that is what
    distinguishes a live model run from the deterministic fixture agent.
    """
    runs = [Run.from_jsonl(line) for line in _read_lines(path)]
    total_out = sum(r.total_tokens_out for r in runs)
    assert total_out > 0, (
        f"{os.path.basename(path)} has zero output tokens across "
        f"{len(runs)} runs — not a real model recording"
    )


def test_narrowed_recording_really_regresses() -> None:
    """Fault detected: the 'regressed' recording stops regressing.

    The narrowed-prompt recording is the gate's regression target; if it ever
    starts calling the required tool the gate demo becomes vacuous.
    """
    narrowed = [p for p in RECORDINGS if os.path.basename(p).startswith("real_gemma3_4b_narrowed")]
    assert narrowed, "narrowed (regressed) recording missing"
    runs = [Run.from_jsonl(line) for line in _read_lines(narrowed[0])]
    calls = [tc.name for r in runs for tc in r.all_tool_calls()]
    assert (
        "search_docs" not in calls
    ), "narrowed recording calls search_docs; the gate would no longer fail on it"
