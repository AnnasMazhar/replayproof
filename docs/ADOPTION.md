# docs/ADOPTION.md — Real-World Adoption Guide

**Pass:** c1-p03-research-3 (real-world applicability)
**Date:** 2026-09-26

This document is for the engineer who has 90 minutes on a Tuesday and wants replayproof
in CI by end of day. It covers the concrete integration path against a named real-world
tool (Inspect AI), the failure modes that will bite first, the ongoing cost to operate,
and the single most likely reason a team would walk away.

---

## The scenario

A team runs `inspect_ai` to evaluate a customer-service agent. They have a working eval
suite (50 samples, `search_knowledge_base` and `get_order_status` as tools) and a green
CI pipeline. They have been burned once: a model upgrade made the agent stop calling
`search_knowledge_base` before answering, which degraded answer quality — but the pass
rate only dropped from 94% to 91%, within noise, so CI stayed green.

Goal: add a gate that catches tool-call contract regressions and cost increases without
breaking the existing Inspect pipeline.

---

## Step 0 — Prerequisites (5 minutes)

Requirements:
- Python 3.11+, `uv` installed, an existing Inspect eval or any JSONL recording
- No API keys required after this setup

```bash
cd your-project/
uv pip install 'agent-eval-harness>=0.1.0'
# or, from source:
uv pip install 'git+https://github.com/openclaw/agent-eval-harness.git@feat/v0.1'
```

Verify:

```
python -c "import agenteval; print(agenteval.__version__)"
0.1.0
```

---

## Step 1 — Capture a recording from Inspect AI (15 minutes)

Inspect AI writes full eval logs (`.eval` archives). In v0.1, replayproof reads its own
JSONL format and OpenAI/Anthropic-style message lists directly. The bridge is one script.

**Option A: Convert an existing Inspect `.eval` log to replayproof JSONL**

```python
# scripts/convert_inspect_log.py
"""Convert an Inspect AI .eval log to replayproof JSONL.

Inspect .eval files are zip archives. Each sample's model_output is a list of
ModelOutput objects. This script unpacks and normalises them to replayproof's
OpenAI-style message format, then writes one Run per sample.
"""
import json
import zipfile
from pathlib import Path
from agenteval.record import from_messages
from agenteval.transcript import Run

def convert(eval_path: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    with zipfile.ZipFile(eval_path) as z:
        with z.open("log.json") as f:
            log = json.load(f)
    samples = log.get("samples", [])
    runs: list[Run] = []
    for sample in samples:
        messages = []
        for event in sample.get("events", []):
            if event.get("event") == "model":
                for msg in event.get("output", {}).get("choices", [{}]):
                    content = msg.get("message", {})
                    messages.append(content)
        if messages:
            run = from_messages(
                messages,
                name=str(sample.get("id", "unknown")),
                agent_id="inspect-agent",
                model=log.get("eval", {}).get("model", "unknown"),
                provider="inspect",
            )
            runs.append(run)
    out_file = out / Path(eval_path).stem
    out_file = out_file.with_suffix(".jsonl")
    with open(out_file, "w") as f:
        for run in runs:
            f.write(run.to_jsonl() + "\n")
    print(f"Wrote {len(runs)} runs to {out_file}")

if __name__ == "__main__":
    import sys
    convert(sys.argv[1], sys.argv[2])
```

Run it:

```bash
python scripts/convert_inspect_log.py logs/customer_service_gpt4o.eval /tmp/recordings/
# Wrote 50 runs to /tmp/recordings/customer_service_gpt4o.jsonl
```

**Option B: Record a fresh run directly**

If the agent is Python-callable (not via Inspect), use the `Recorder` directly:

```python
from agenteval.record import Recorder

def my_agent(task: str, tools: dict) -> str:
    # ... your agent implementation
    pass

tools = {
    "search_knowledge_base": lambda query: {"results": ["doc1", "doc2"]},
    "get_order_status": lambda order_id: {"status": "shipped"},
}

with Recorder(agent=my_agent, tools=tools) as recorder:
    result = recorder.record(task="What is the status of order 12345?")
    run = recorder.run  # agenteval.transcript.Run

with open("recordings/baseline.jsonl", "w") as f:
    f.write(run.to_jsonl())
```

---

## Step 2 — Write a contract (10 minutes)

Create `contracts/customer_service.yaml`:

```yaml
# contracts/customer_service.yaml
# Contract for the customer-service agent.
# Fault this detects: agent answers without consulting the knowledge base (regression
# introduced by model upgrade that makes the agent skip tool calls on "obvious" questions).
checks:
  - id: cs-001
    type: required_tools
    severity: error
    description: "Agent must call search_knowledge_base before every answer"
    names:
      - search_knowledge_base

  - id: cs-002
    type: tool_sequence
    severity: error
    description: "search_knowledge_base must precede final answer (ordered)"
    tools:
      - search_knowledge_base
    ordered: true

  - id: cs-003
    type: forbidden_tools
    severity: warn
    description: "Agent must not call get_internal_debug_info (internal tool leaked in prompt)"
    names:
      - get_internal_debug_info

  - id: cs-004
    type: arg_schema
    severity: error
    description: "search_knowledge_base query must be a non-empty string"
    tool: search_knowledge_base
    schema:
      type: object
      required: [query]
      properties:
        query:
          type: string
          minLength: 1

  - id: cs-005
    type: no_pattern
    severity: error
    description: "Final answer must not contain email addresses (PII leak)"
    field: content
    regex: "[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,}"

  - id: cs-006
    type: max_tool_calls
    severity: warn
    description: "Agent must not call more than 8 tools per turn (runaway tool use)"
    n: 8

  - id: cs-007
    type: max_tokens
    severity: warn
    description: "Total tokens must not exceed 4000 per run (cost gate)"
    n: 4000
```

---

## Step 3 — Evaluate a recording and store a baseline (10 minutes)

```bash
# Evaluate the recording against the contract
agenteval run \
    --contract contracts/customer_service.yaml \
    --runs /tmp/recordings/customer_service_gpt4o.jsonl \
    --output baselines/customer_service_gpt4o.json

# Inspect the result
cat baselines/customer_service_gpt4o.json | python -m json.tool | head -30
```

Expected output (trimmed):

```
{
  "pass_rate": 0.94,
  "wilson_lower": 0.832,
  "total_tokens_in": 124000,
  "total_tokens_out": 31500,
  "p95_latency_ms": 0.1,
  "cases": [...]
}
```

The `wilson_lower` of 0.832 tells you: even at 94% observed pass rate on 50 cases, the
true pass rate could be as low as 83% at 95% confidence. If the next run drops to
wilson_lower < 0.832, that is a meaningful regression, not noise.

Commit the baseline:

```bash
git add baselines/customer_service_gpt4o.json
git commit -m "chore: store eval baseline for customer-service contract"
```

---

## Step 4 — Gate in CI (10 minutes)

Add to `.github/workflows/eval.yml`:

```yaml
name: eval-gate
on:
  push:
    branches: [main]
  pull_request:
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install 'agent-eval-harness>=0.1.0'

      # 1. Evaluate the current recordings
      - name: Evaluate runs against contract
        run: |
          agenteval run \
            --contract contracts/customer_service.yaml \
            --runs recordings/customer_service_latest.jsonl \
            --output /tmp/current_result.json

      # 2. Gate against the stored baseline
      - name: Gate — fail on regression
        run: |
          agenteval gate \
            --baseline baselines/customer_service_gpt4o.json \
            --current /tmp/current_result.json
        # exits 1 if pass_rate dropped, tokens increased >10%, cost increased >10%,
        # or p95 latency increased >25%; exits 0 otherwise
```

That is the full integration. Step 4 is optional for teams that generate fresh recordings
in CI: replace `recordings/customer_service_latest.jsonl` with the output of whatever
generates your recordings.

---

## Step 5 — Drift report after a model swap (5 minutes)

When you upgrade from GPT-4o to GPT-4.5:

```bash
agenteval run \
    --contract contracts/customer_service.yaml \
    --runs recordings/customer_service_gpt45.jsonl \
    --output /tmp/gpt45_result.json

agenteval drift \
    --a baselines/customer_service_gpt4o.json \
    --b /tmp/gpt45_result.json \
    --format md
```

Output excerpt:

```
## Drift report

| Case | Before | After | Verdict |
|------|--------|-------|---------|
| case_07 | pass | fail | regression |
| case_14 | fail | pass | fix |
| case_22 | pass | fail | regression |

Regressions: 2 | Fixes: 1 | Stable pass: 47
```

The regressions show *which cases* moved. Each failure row includes the broken check id
(`cs-001: required_tools not satisfied`), so the team knows immediately that the model
is skipping `search_knowledge_base` on those specific inputs — not that "something
changed in the eval".

---

## Production failure modes (what will actually break)

### FM-1: Baseline drift — the committed baseline goes stale

**When:** The agent's recording fixture is regenerated (new fixtures from a new model or
prompt change), but the baseline JSON was committed from an older fixture set.

**Symptom:** The gate trips on every CI run even though nothing regressed, because the
token counts in the new recordings differ from the baseline by >10%.

**Fix:** Re-run `agenteval run` against the new recordings and commit the new baseline.
The gate only compares what you committed; it has no way to distinguish "baseline is stale"
from "current run regressed". Detection: if the gate trips on `main` immediately after a
known-clean merge, the baseline is probably stale.

**Operational note:** Treat the baseline JSON like a lock file. When you intentionally
change the agent (new prompt, new model), update and commit the baseline in the same PR.
A baseline update PR without a corresponding recording change should fail code review.

### FM-2: Recording format mismatch — Inspect `.eval` not natively supported in v0.1

**When:** A team tries to point replayproof directly at an Inspect `.eval` log file.

**Symptom:** `agenteval run` raises `ValueError: unrecognised transcript format` or
silently produces zero cases (empty run).

**Fix:** Use the conversion script from Step 1. The bridge is 30 lines and has no
dependencies beyond the standard library and replayproof itself. It is not in the
package yet; it lives in `scripts/` in your project.

**Operational note:** An Inspect `.eval` reader is planned (see roadmap in `README.md`).
Until it lands, every team using Inspect must maintain this bridge. This is the friction
cost of v0.1 for the most common integration target.

### FM-3: PII detection false positives on structured IDs

**When:** An agent's tool arguments include structured IDs that match the email regex
pattern — for example, `user_ref="A.B.C@internal"` in a ticketing system namespace, or
a UUID formatted as `prefix@suffix` in an event bus.

**Symptom:** `cs-005` (no_pattern check for email) fires on every run, failing the suite.

**Fix:** Refine the regex in the contract to exclude known-safe patterns:

```yaml
- id: cs-005
  type: no_pattern
  severity: error
  field: content
  # exclude internal ticketing refs (A.B.@internal patterns) from the PII check
  regex: "(?<!@internal)[a-zA-Z0-9._%+\\-]+@(?!internal)[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,}"
```

Or use `severity: warn` for the email check until the pattern is tuned.

**Root cause:** The PII_PATTERNS dict is intentionally broad. Regex-based PII detection
has a precision–recall tradeoff; a broad pattern catches more real leaks at the cost of
more false positives in structured-ID-heavy codebases. The README documents this as a
known limitation.

### FM-4: Wilson lower bound looks alarming on small suites

**When:** A team evaluating a new feature with 6 test cases sees `wilson_lower: 0.35`
even though 6/6 cases passed.

**Symptom:** Stakeholders see 35% in the CI report and assume something is broken.

**Fix:** Label the metric correctly in your CI output:

```bash
agenteval run ... --format md | grep -A5 "Wilson"
# Wilson Lower Bound (95%): 35.0%  ← "minimum plausible pass rate at 95% confidence"
```

Document in your team's eval runbook: "A lower bound of 35% on 6/6 means we cannot
claim the agent reliably passes >35% of future cases; it does NOT mean we observed a
35% pass rate. Grow the suite to n≥30 for a useful absolute lower bound."

**Operational note:** For suites with n < 10, the gate should be configured to use
relative regression (`max_pass_rate_drop = 0.0`) rather than an absolute Wilson
threshold. The default configuration already does this.

### FM-5: Dry-mode replay passes, live fails (side-effect gap)

**When:** A tool writes to a database and a subsequent tool reads back what was written.
In dry mode, both the write (result: `{"status": "ok"}`) and the subsequent read
(result: `{"data": [...]}`) are replayed from the recording. The gate passes. In live
execution, the write fails silently, the read returns stale data, and the agent gives
a wrong answer.

**Symptom:** CI consistently green, production sometimes wrong on the exact same inputs.

**Fix:** This is the documented scope boundary. Dry-mode replay tests the deterministic
scaffold (routing, contract checks, token budgets). It does not test external state. For
side-effecting tools, maintain an integration test that runs live against a staging
environment, and use replayproof for the CI layer that must be keyless.

---

## Operational cost

### In CI

- Runtime: 0–5 ms per case evaluation (no model calls; all regex and data-structure
  comparison). A 50-case suite completes in under 50 ms of wall time. Dominant cost is
  Python startup (~0.5 s) and loading JSONL from disk.
- Storage: each baseline JSON is ~10–30 KB per 50 cases. No database. No server.
  Files live in the repo next to the code.
- Dependencies added to CI: none beyond `pyyaml` and `jsonschema` (both stdlib-weight
  libraries). No Docker, no MLflow server, no network.

### Maintenance burden

- **Per model upgrade:** re-run `agenteval run`, inspect drift output, commit new
  baseline. ~15 minutes.
- **Per agent change:** update the contract YAML if new tools are added or removed.
  5–10 minutes per change.
- **Per new contract:** write the YAML (see template in Step 2), run once to capture
  baseline. 20–30 minutes for a new agent.
- **Baseline rot:** if recordings are regenerated quarterly, baselines must be
  refreshed quarterly. If recordings are static fixtures, baselines are stable.

### What this does not cost

- No API calls. No vendor account. No secrets in CI.
- No background processes. No daemon. No database migrations.
- No binary dependencies. Pure Python + two pure-Python libraries.

---

## The one reason a team would not adopt this

**The contract must be written by someone who knows what the agent is supposed to do.**

`required_tools`, `forbidden_tools`, `tool_sequence` — these are only useful if the
engineer filling out the YAML understands the agent's intended behaviour. A team that
cannot articulate "this agent must call `search_knowledge_base` before answering" has
no way to write a contract, and without a contract, the gate degrades to a token-count
alarm.

This is not a shortcoming of the tool; it is the nature of contract testing. The
prerequisite is specification. Teams that run evals without a written specification of
what correct agent behaviour looks like will find the contract YAML blank. They will
default to `max_tokens` and `max_tool_calls` as their only checks, which is weaker than
what most eval frameworks provide out of the box.

The adoption blocker, stated plainly: **if a team does not know what their agent should
do, this tool cannot tell them**. It enforces a spec you provide; it does not generate
one.

Teams most likely to succeed: those who already maintain a written runbook for their
agent (what tools it must call, what it must not emit, what its token budget is) and want
to automate that runbook as a CI check. Teams least likely to succeed: those still in
exploratory development, running evals to learn what the agent does rather than to verify
what it should do.

---

## Summary: adoption decision tree

```
Does your team have eval recordings already?
├── Yes (Inspect .eval, OpenAI JSONL, etc.)
│   └── Can you articulate what tools the agent must/must-not call?
│       ├── Yes → adopt replayproof. Step 1-4 takes 40 minutes.
│       └── No  → write the spec first. Come back when you have it.
└── No recordings yet
    ├── Are you using Inspect AI? → run one eval, then Step 1-4.
    └── Calling the agent directly in Python? → use Recorder, then Step 2-4.
```
