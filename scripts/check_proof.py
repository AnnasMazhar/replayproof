#!/usr/bin/env python3
"""check_proof.py — validate that agent-eval-harness satisfies its acceptance criteria.

The repo's proof is:
1. All tests pass (pytest -q exits 0)
2. The demo runs end-to-end (bash examples/run_demo.sh exits 0)
3. The gate correctly distinguishes good from regressed runs:
   - gate(good vs good) exits 0
   - gate(good vs regressed) exits 1

This checker is falsifiable: removing EVIDENCE.md, breaking a test, or making the
gate exit incorrectly will cause the checker to fail and print which check broke.

Exits 0 and prints PROOF_COMPLETE on success.
Exits 1 with a clear message on any failure.

Usage:
    python scripts/check_proof.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVIDENCE_MD = _REPO_ROOT / "EVIDENCE.md"
_VENV_PYTEST = _REPO_ROOT / ".venv" / "bin" / "pytest"
_VENV_AGENTEVAL = _REPO_ROOT / ".venv" / "bin" / "agenteval"
_DEMO_SCRIPT = _REPO_ROOT / "examples" / "run_demo.sh"
_SAMPLE_RUN = _REPO_ROOT / "examples" / "recordings" / "sample_run.jsonl"
_REGRESSED_RUN = _REPO_ROOT / "examples" / "recordings" / "regressed_run.jsonl"
_CONTRACT = _REPO_ROOT / "examples" / "contracts" / "research.yaml"

MIN_TEST_COUNT = 200  # Must have at least this many tests


def check_evidence_exists() -> list[str]:
    """Check that EVIDENCE.md exists and is non-empty."""
    if not _EVIDENCE_MD.exists():
        return [f"MISSING: {_EVIDENCE_MD.name} does not exist"]
    if _EVIDENCE_MD.stat().st_size < 1000:
        return [f"INCOMPLETE: {_EVIDENCE_MD.name} is too small (< 1000 bytes)"]
    return []


def check_venv_exists() -> list[str]:
    """Check that the venv and required tools exist."""
    fails = []
    if not _VENV_PYTEST.exists():
        fails.append(f"MISSING: {_VENV_PYTEST} — run: uv venv && uv pip install -e '.[dev]'")
    if not _VENV_AGENTEVAL.exists():
        fails.append(f"MISSING: {_VENV_AGENTEVAL} — run: uv venv && uv pip install -e '.[dev]'")
    return fails


def check_tests_pass() -> list[str]:
    """Run pytest and verify all tests pass with at least MIN_TEST_COUNT tests."""
    if not _VENV_PYTEST.exists():
        return ["SKIP: pytest not installed (venv missing)"]
    
    result = subprocess.run(
        [str(_VENV_PYTEST), "-q", "--tb=no"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    
    if result.returncode != 0:
        # Extract the summary line
        lines = (result.stdout + result.stderr).strip().splitlines()
        summary = [l for l in lines if "passed" in l.lower() or "failed" in l.lower()]
        return [f"TESTS FAILED: pytest exited {result.returncode}"] + summary[-3:]
    
    # Parse test count from output (e.g., "220 passed in 8.52s")
    output = result.stdout + result.stderr
    import re
    match = re.search(r"(\d+)\s+passed", output)
    if match:
        count = int(match.group(1))
        if count < MIN_TEST_COUNT:
            return [f"INSUFFICIENT TESTS: {count} < {MIN_TEST_COUNT} required"]
    
    return []


def check_demo_runs() -> list[str]:
    """Run the demo script and verify it completes successfully."""
    if not _DEMO_SCRIPT.exists():
        return [f"MISSING: {_DEMO_SCRIPT}"]
    
    result = subprocess.run(
        ["bash", str(_DEMO_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    
    if result.returncode != 0:
        lines = (result.stdout + result.stderr).strip().splitlines()
        return [f"DEMO FAILED: {_DEMO_SCRIPT.name} exited {result.returncode}"] + lines[-5:]
    
    # Verify the demo actually ran the final checks
    if "PASS: gate exits correctly" not in result.stdout:
        return ["DEMO INCOMPLETE: did not reach 'PASS: gate exits correctly'"]
    
    return []


def check_gate_distinguishes() -> list[str]:
    """Verify the gate command correctly exits 0 on good, 1 on regressed."""
    if not _VENV_AGENTEVAL.exists():
        return ["SKIP: agenteval not installed (venv missing)"]
    
    fails = []
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        good_result = Path(tmpdir) / "good.json"
        bad_result = Path(tmpdir) / "bad.json"
        
        # Run against good
        r1 = subprocess.run(
            [str(_VENV_AGENTEVAL), "run",
             "--contract", str(_CONTRACT),
             "--runs", str(_SAMPLE_RUN),
             "--output", str(good_result)],
            capture_output=True,
            cwd=_REPO_ROOT,
        )
        if r1.returncode != 0:
            return [f"EVAL GOOD FAILED: agenteval run exited {r1.returncode}"]
        
        # Run against regressed
        r2 = subprocess.run(
            [str(_VENV_AGENTEVAL), "run",
             "--contract", str(_CONTRACT),
             "--runs", str(_REGRESSED_RUN),
             "--output", str(bad_result)],
            capture_output=True,
            cwd=_REPO_ROOT,
        )
        if r2.returncode != 0:
            return [f"EVAL REGRESSED FAILED: agenteval run exited {r2.returncode}"]
        
        # Gate: good vs good should exit 0
        r3 = subprocess.run(
            [str(_VENV_AGENTEVAL), "gate",
             "--baseline", str(good_result),
             "--current", str(good_result)],
            capture_output=True,
            cwd=_REPO_ROOT,
        )
        if r3.returncode != 0:
            fails.append(f"GATE GOOD FAILED: gate(good, good) exited {r3.returncode}, expected 0")
        
        # Gate: good vs regressed should exit 1
        r4 = subprocess.run(
            [str(_VENV_AGENTEVAL), "gate",
             "--baseline", str(good_result),
             "--current", str(bad_result)],
            capture_output=True,
            cwd=_REPO_ROOT,
        )
        if r4.returncode != 1:
            fails.append(f"GATE REGRESSED FAILED: gate(good, regressed) exited {r4.returncode}, expected 1")
    
    return fails


def check_fixtures_exist() -> list[str]:
    """Verify the fixture files exist."""
    fails = []
    for path in [_SAMPLE_RUN, _REGRESSED_RUN, _CONTRACT]:
        if not path.exists():
            fails.append(f"MISSING FIXTURE: {path.relative_to(_REPO_ROOT)}")
    return fails


def main() -> int:
    all_failures: list[str] = []
    
    print("check_proof: validating agent-eval-harness proof...")
    
    # Quick checks first
    print("  [1/6] Checking EVIDENCE.md exists...")
    all_failures.extend(check_evidence_exists())
    
    print("  [2/6] Checking fixtures exist...")
    all_failures.extend(check_fixtures_exist())
    
    print("  [3/6] Checking venv exists...")
    all_failures.extend(check_venv_exists())
    
    # If venv is missing, skip the rest
    if any("venv missing" in f or "uv venv" in f for f in all_failures):
        print("check_proof: FAIL (venv not set up)")
        for f in all_failures:
            print(f"  {f}")
        return 1
    
    print("  [4/6] Running pytest...")
    all_failures.extend(check_tests_pass())
    
    print("  [5/6] Running demo script...")
    all_failures.extend(check_demo_runs())
    
    print("  [6/6] Verifying gate distinguishes good from regressed...")
    all_failures.extend(check_gate_distinguishes())
    
    if all_failures:
        print("check_proof: FAIL")
        for f in all_failures:
            print(f"  {f}")
        return 1
    
    print("check_proof: all checks passed.")
    print("PROOF_COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
