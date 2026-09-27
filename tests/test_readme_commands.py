"""Assert the README's first command block runs verbatim from a fresh clone.

Fault detected: a README quickstart that a new visitor cannot run as written (wrong paths, a
missing baseline, or a gate that never fails). This test exists because the published README
referenced `recordings/sample_run.jsonl` and `baseline.json`, neither of which was in the repo.

The three commands below are copied from README.md ("What problem this solves" block) with only
the output paths redirected into a temp directory.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "contracts" / "research.yaml"
SAMPLE = REPO / "examples" / "recordings" / "sample_run.jsonl"
REGRESSED = REPO / "examples" / "recordings" / "regressed_run.jsonl"


def _agenteval() -> str:
    """The console script installed alongside the interpreter running the tests."""
    exe = Path(sys.executable).parent / "agenteval"
    assert exe.exists(), f"console script not found at {exe} — was the package installed?"
    return str(exe)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)


def test_readme_quickstart_runs_verbatim(tmp_path: Path) -> None:
    for path in (CONTRACT, SAMPLE, REGRESSED):
        assert path.exists(), f"README references a file that does not exist: {path}"

    baseline = tmp_path / "baseline.json"
    result = tmp_path / "result.json"

    # 1. record a run once — becomes the baseline
    r1 = _run([_agenteval(), "run", "--contract", str(CONTRACT),
               "--runs", str(SAMPLE), "--output", str(baseline)], tmp_path)
    assert r1.returncode == 0, f"step 1 failed:\n{r1.stdout}\n{r1.stderr}"
    assert baseline.exists(), "step 1 produced no baseline file"

    # 2. record again — a run whose tool-call contract regressed
    r2 = _run([_agenteval(), "run", "--contract", str(CONTRACT),
               "--runs", str(REGRESSED), "--output", str(result)], tmp_path)
    assert r2.returncode == 0, f"step 2 failed:\n{r2.stdout}\n{r2.stderr}"

    # 3. gate it — must exit 1 on the regression (a gate that cannot fail is not a gate)
    r3 = _run([_agenteval(), "gate", "--baseline", str(baseline),
               "--current", str(result)], tmp_path)
    assert r3.returncode == 1, (
        "gate must exit 1 on the regressed run as the README states; "
        f"got {r3.returncode}\n{r3.stdout}\n{r3.stderr}"
    )
