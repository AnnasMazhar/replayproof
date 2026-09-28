#!/usr/bin/env bash
# docs/demo.sh — record an asciinema demo of replayproof
#
# PREREQUISITES
#   pip install asciinema          (or brew install asciinema)
#   uv venv && uv pip install -e '.[dev]'
#
# RECORDING
#   bash docs/demo.sh
#   This records to /tmp/replayproof-demo.cast (~ 60 seconds).
#
# CONVERTING TO GIF (for README hero image)
#   pip install agg                # or: cargo install agg
#   agg /tmp/replayproof-demo.cast docs/demo.gif --speed 1.5 --theme monokai
#   # Then link in README: ![demo](docs/demo.gif)
#
# UPLOADING TO asciinema.org (optional share link)
#   asciinema upload /tmp/replayproof-demo.cast
#
# REPRODUCIBILITY
#   The demo uses committed fixture recordings — no LLM call, no network.
#   Running it twice produces output that is identical up to wall-clock timing.

set -euo pipefail

CAST=/tmp/replayproof-demo.cast
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v asciinema &>/dev/null; then
    echo "asciinema not found — install it first: pip install asciinema" >&2
    exit 1
fi

cd "$REPO_ROOT"

# Verify the venv exists; if not, build it.
if [[ ! -f ".venv/bin/agenteval" ]]; then
    echo "Building venv…"
    uv venv
    uv pip install -e '.[dev]'
fi

echo "Recording to $CAST …"
echo "Press Ctrl+D or type 'exit' when done to stop the recording."

asciinema rec "$CAST" --title "replayproof — offline LLM agent regression testing" \
    --command "bash -c '
echo \"=== replayproof — offline LLM agent regression testing ===\"
echo
echo \"1) Evaluate the good run against a YAML contract\"
.venv/bin/agenteval run \\
    --contract examples/contracts/research.yaml \\
    --runs examples/recordings/sample_run.jsonl \\
    --output /tmp/demo_good.json
echo
echo \"2) Gate: good run vs itself (expect exit 0)\"
.venv/bin/agenteval gate \\
    --baseline /tmp/demo_good.json \\
    --current /tmp/demo_good.json
echo \"exit \$? — PASS\"
echo
echo \"3) Evaluate a regressed run\"
.venv/bin/agenteval run \\
    --contract examples/contracts/research.yaml \\
    --runs examples/recordings/regressed_run.jsonl \\
    --output /tmp/demo_regressed.json
echo
echo \"4) Gate: regressed run vs good baseline (expect exit 1)\"
.venv/bin/agenteval gate \\
    --baseline /tmp/demo_good.json \\
    --current /tmp/demo_regressed.json || true
echo
echo \"5) Drift report — which cases regressed?\"
.venv/bin/agenteval drift \\
    --a /tmp/demo_good.json \\
    --b /tmp/demo_regressed.json
echo
echo \"=== No API keys used. All output from committed fixtures. ===\"
'"

echo
echo "Saved to $CAST"
echo
echo "Next steps:"
echo "  Convert to GIF:  agg $CAST docs/demo.gif --speed 1.5 --theme monokai"
echo "  Upload:          asciinema upload $CAST"
