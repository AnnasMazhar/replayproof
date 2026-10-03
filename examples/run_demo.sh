#!/usr/bin/env bash
# examples/run_demo.sh — end-to-end demo of record -> gate -> drift -> report
# Requires: uv venv && uv pip install -e '.[dev]' already run in repo root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="$REPO_ROOT/.venv/bin/python"
AGENTEVAL="${AGENTEVAL:-$REPO_ROOT/.venv/bin/agenteval}"

echo "=== replayproof demo ==="
echo ""

# Step 1: run the contract against the sample (good) run
echo "--- Step 1: evaluate sample_run.jsonl against research contract ---"
"$AGENTEVAL" run \
    --contract "$SCRIPT_DIR/contracts/research.yaml" \
    --runs "$SCRIPT_DIR/recordings/sample_run.jsonl" \
    --output "$SCRIPT_DIR/recordings/sample_result.json" \
    --format md
echo ""

# Step 2: run the contract against the regressed run
echo "--- Step 2: evaluate regressed_run.jsonl against research contract ---"
"$AGENTEVAL" run \
    --contract "$SCRIPT_DIR/contracts/research.yaml" \
    --runs "$SCRIPT_DIR/recordings/regressed_run.jsonl" \
    --output "$SCRIPT_DIR/recordings/regressed_result.json" \
    --format md
echo ""

# Step 3: gate — good run vs itself (should PASS)
echo "--- Step 3: gate good run vs itself (expect: PASS, exit 0) ---"
set +e
"$AGENTEVAL" gate \
    --baseline "$SCRIPT_DIR/recordings/sample_result.json" \
    --current "$SCRIPT_DIR/recordings/sample_result.json"
GATE_GOOD=$?
set -e
echo "Exit code: $GATE_GOOD"
echo ""

# Step 4: gate — regressed run vs good baseline (should FAIL, exit 1)
echo "--- Step 4: gate regressed run vs good baseline (expect: FAIL, exit 1) ---"
set +e
"$AGENTEVAL" gate \
    --baseline "$SCRIPT_DIR/recordings/sample_result.json" \
    --current "$SCRIPT_DIR/recordings/regressed_result.json"
GATE_BAD=$?
set -e
echo "Exit code: $GATE_BAD"
echo ""

# Step 5: drift — diff the two runs
echo "--- Step 5: drift report ---"
"$AGENTEVAL" drift \
    --a "$SCRIPT_DIR/recordings/sample_result.json" \
    --b "$SCRIPT_DIR/recordings/regressed_result.json"
echo ""

# Step 6: render markdown report for the regressed run
echo "--- Step 6: markdown report for regressed run ---"
"$AGENTEVAL" report \
    --suite "$SCRIPT_DIR/recordings/regressed_result.json" \
    --format md
echo ""

# Final validation
echo "--- Final checks ---"
if [ "$GATE_GOOD" -ne 0 ]; then
    echo "FAIL: gate on good run should exit 0, got $GATE_GOOD" >&2
    exit 1
fi
if [ "$GATE_BAD" -ne 1 ]; then
    echo "FAIL: gate on regressed run should exit 1, got $GATE_BAD" >&2
    exit 1
fi
echo "PASS: gate exits correctly (0 on good, 1 on regressed)"
echo ""
echo "=== Demo complete ==="
