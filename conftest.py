"""Root conftest.py — sets REPO_ROOT so tests that read repository files
(e.g. README.md) can locate them regardless of whether pytest is run from the
normal test tree or from the mutmut-generated mutants/ directory."""

import os
from pathlib import Path

# Walk up from this file's directory until we find README.md.
# Use README.md (not pyproject.toml) as the anchor because mutants/ also has pyproject.toml.
_candidate = Path(__file__).resolve().parent
while not (_candidate / "README.md").exists() and _candidate.parent != _candidate:
    _candidate = _candidate.parent

if (_candidate / "README.md").exists():
    os.environ.setdefault("REPO_ROOT", str(_candidate))
