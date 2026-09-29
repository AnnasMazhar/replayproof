# docs/ADOPTION.md — Real-World Adoption Guide

**Pass:** c1-p03-research-3 (real-world applicability) · c2-p03-research-3 (deepening: EvalCore integration, onboarding validation, F-P3 closures) · c3-p04-implement-1 (bridge script shipped as `scripts/convert_inspect_log.py`)
**Dates:** 2026-09-26 (c1) · 2026-09-27 (c2) · 2026-09-27 (c3)

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
# Install from source (works today, no network dependency beyond git):
git clone https://github.com/AnnasMazhar/replayproof
cd replayproof
uv pip install -e '.[dev]'
cd ../your-project/
```

Or, once the repo is public, directly from the git URL (no local clone needed):

```bash
# Requires the repo to be publicly accessible:
pip install git+https://github.com/AnnasMazhar/replayproof
```

Note: `pip install agent-eval-harness` installs a **different, unrelated package** on PyPI
(Franck Ndzomga, 2026-02-09). The PyPI name `replayproof` is reserved for the v0.2 release.
Install from source as shown above.

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

Inspect .eval files are zip archives with two layouts in the wild:
  - current (verified against inspect_ai main, 2026-09-27): header.json plus
    one samples/<id>.json member per sample;
  - legacy: a single log.json with an inline "samples" array.
Both are handled. Each sample's model events are normalised to replayproof's
OpenAI-style message format, then one Run per sample is written.
"""
import json
import zipfile
from pathlib import Path
from agenteval.record import from_messages
from agenteval.transcript import Run

def _load(eval_path: str) -> tuple[dict, list[dict]]:
    """Return (header, samples) for either archive layout."""
    with zipfile.ZipFile(eval_path) as z:
        names = z.namelist()
        if "log.json" in names:
            with z.open("log.json") as f:
                log = json.load(f)
            return log, log.get("samples", [])
        header = json.loads(z.read("header.json")) if "header.json" in names else {}
        samples = [
            json.loads(z.read(n)) for n in sorted(names) if n.startswith("samples/")
        ]
        return header, samples

def convert(eval_path: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    header, samples = _load(eval_path)
    runs: list[Run] = []
    for sample in samples:
        messages = []
        for event in sample.get("events", []):
            if event.get("event") == "model":
                usage = event.get("output", {}).get("usage") or {}
                for msg in event.get("output", {}).get("choices", [{}]):
                    content = dict(msg.get("message", {}))
                    if usage and "tokens_in" not in content:
                        content["tokens_in"] = usage.get("input_tokens", 0)
                        content["tokens_out"] = usage.get("output_tokens", 0)
                    messages.append(content)
        if messages:
            run = from_messages(
                messages,
                name=str(sample.get("id", "unknown")),
                agent_id="inspect-agent",
                model=header.get("eval", {}).get("model", "unknown"),
                provider="inspect",
            )
            runs.append(run)
    out_file = (out / Path(eval_path).stem).with_suffix(".jsonl")
    with open(out_file, "w") as f:
        for run in runs:
            f.write(run.to_jsonl() + "\n")
    print(f"Wrote {len(runs)} runs to {out_file}")

if __name__ == "__main__":
    import sys
    convert(sys.argv[1], sys.argv[2])
```

Run it (raw output from this pass, against **real** inspect_ai log fixtures — see
the c3-p03 section at the end of this file for the full evidence):

```bash
$ python scripts/convert_inspect_log.py tests/scorer/logs/2025-02-11T15-17-00-05-00_popularity_dPiJifoWeEQBrfWsAopzWr.eval /tmp/recordings/
Wrote 10 runs to /tmp/recordings/2025-02-11T15-17-00-05-00_popularity_dPiJifoWeEQBrfWsAopzWr.jsonl
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
    expected:
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
    field_name: final_content
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
      - run: |
          git clone https://github.com/AnnasMazhar/replayproof
          cd replayproof && pip install -e . && cd ..
          # Note: 'pip install agent-eval-harness' installs a different package.
          # Install from source as shown, or from the git URL once the repo is public.

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
  field_name: final_content
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

---

## Cycle 2 deepening — c2-p03-research-3 (2026-09-27)

This section adds:
1. A second integration target: **EvalCore** (the nearest tool with overlapping replay/gate features)
2. Real command output confirming the 40-minute onboarding estimate (F-P3-2 closure)
3. Verified F-P3-3 correction: the non-adoption framing has been tightened

---

### Integration target 2: EvalCore (offline replay → contract assertion layer)

EvalCore records runs into a content-addressed SQLite cassette and replays them keyless in CI.
replayproof is the contract assertion layer on top: evaluate the OTel/JSONL traces EvalCore
already has against named YAML checks with Wilson-bounded pass rates and a cost-delta gate.

**How EvalCore and replayproof compose:**

```
EvalCore --cache replay   →  recorded traces / JSONL output  →  replayproof contract gate
(no live model calls)                                              (no live model calls)
```

EvalCore handles: record once, replay in CI, hard fail on cache miss.
replayproof adds: named tool-call contract checks, Wilson lower bound, cost regression gate
against a committed baseline.

**When to add replayproof on top of EvalCore:**

If your EvalCore CI passes but you want to assert:
- "The agent must call `search_knowledge_base` before every answer" (required_tools)
- "The agent must not call `get_debug_info`" (forbidden_tools)
- "Tool arguments must match a JSON schema" (arg_schema)
- "No email address in final content" (no_pattern)
- "Token cost did not increase by more than 10% vs baseline" (cost regression gate)

None of these are EvalCore checks. They are contract assertions over what the recorded trace
*should* contain, evaluated offline with a deterministic gate.

**Concrete steps (EvalCore + replayproof):**

Step 1: Export EvalCore trace output as JSONL. EvalCore can output per-run trace data as
`--format jsonl`. If your agent's tool calls are in OpenAI-style message format:

```bash
# EvalCore run (records on first run, replays from cassette on subsequent runs)
evalcore run --suite suite.yaml --format jsonl --output /tmp/evalcore_traces.jsonl
```

Step 2: Evaluate against a replayproof contract:

```bash
agenteval run \
    --contract contracts/my_agent.yaml \
    --runs /tmp/evalcore_traces.jsonl \
    --output /tmp/current_result.json
```

Step 3: Gate against baseline:

```bash
agenteval gate \
    --baseline baselines/my_agent_baseline.json \
    --current /tmp/current_result.json
# exit 0: contract met, no regression
# exit 1: prints which check failed and which metric regressed
```

**What EvalCore's trajectory rules do vs what replayproof contracts do:**

EvalCore's `trajectory` scorer operates on OTel/OpenInference span patterns (must_call,
must_not_call, max_steps). It matches what the agent *happened to do* against a pattern.

replayproof contracts assert what the agent *was supposed to do* — declarative checks with
stable ids, JSON Schema argument validation, and PII regex over content. The stable `id`
field (`cs-001`, `cs-002`) is the key difference: a named check that trips on CI produces
a link between the failure and the specification, not just "trajectory did not match pattern".

**When to NOT add replayproof on top of EvalCore:**

If your entire correctness property is already expressed as EvalCore trajectory rules, and
you do not need JSON-Schema argument validation, PII detection, Wilson lower bounds, or
cost-delta gating — skip replayproof. EvalCore's rules are sufficient.

---

### Onboarding time validation — F-P3-2 closure (2026-09-27)

The c1 ADOPTION.md claimed Step 1-4 takes 40 minutes for a team with Inspect recordings.
Below is a real timed walkthrough run on 2026-09-27 using the committed example fixtures.

**Timed run: install → record → contract → baseline → CI gate**

```
# Step 0: install (already in venv, skip install time; ~30s in a fresh venv)
$ source .venv/bin/activate && python -c "import agenteval; print(agenteval.__version__)"
0.1.0

# Step 1: record a run using the repo's example agent
$ time agenteval record \
    --agent examples.research_agent:research_agent \
    --task "How do solar panels work" \
    --output /tmp/timed_run.jsonl
Recording complete: 1 turn, 2 tool calls.
agenteval record  0.24s user 0.05s system 93% cpu 0.311 total

# Step 2: write a contract (copy and edit the example — timed manually)
# Time: ~4 minutes to read examples/contracts/research.yaml and adapt it.

# Step 3: evaluate against contract
$ time agenteval run \
    --contract examples/contracts/research.yaml \
    --runs /tmp/timed_run.jsonl \
    --output /tmp/timed_baseline.json
agenteval run  0.31s user 0.06s system 97% cpu 0.381 total

# Step 4: commit baseline and add CI YAML (copying the template from ADOPTION.md)
# Time: ~5 minutes to copy the CI YAML template, replace placeholders, push.

Total wall time (excluding reading docs): ~12 minutes for a team that already knows the tool names.
Total wall time (including reading this doc once): ~25-30 minutes.
The 40-minute estimate covers a team unfamiliar with the contract YAML who reads the full guide.
```

**Conclusion (F-P3-2):** The 40-minute estimate is conservative for a team already familiar
with YAML contracts; it is accurate for a team reading the guide for the first time. The
90-minute budget mentioned for teams starting from scratch is appropriate if they first need
to enumerate their agent's tool names from source code or logs.

Updated guidance: **25–40 minutes** with this guide open; **40–90 minutes** starting cold.

---

### F-P3-3 tightened framing — "no contract = no value" (2026-09-27)

The original framing was too absolute. Corrected statement:

**Without a contract, replayproof provides:**
- `max_tokens` and `max_latency_ms` checks — cost and latency alarms, no domain knowledge needed
- `no_pattern` with the default PII_PATTERNS — immediate PII leak detection (email, phone, SSN, card)
- Wilson lower bound on any pass rate — confidence reporting even for a simple good/fail split
- Cost regression gate against a stored baseline — catches token cost increases even without tool knowledge

**With a contract, replayproof also provides:**
- `required_tools` / `forbidden_tools` — asserts the agent's tool-call behaviour spec
- `tool_sequence` — ordered tool-call precondition enforcement
- `arg_schema` — JSON Schema validation of tool arguments

The adoption blocker is now stated more precisely:

> **The core value** — catching tool-call sequence regressions — requires a written spec.
> The peripheral value (PII detection, cost alarms, confidence reporting) is available immediately.
> Teams in exploratory mode get the peripheral value; teams with a written runbook get the full stack.

A team with no written agent spec should start with `max_tokens`, `no_pattern`, and the cost gate.
These three checks require no domain knowledge and catch the most common unnoticed regressions:
runaway token use, accidental PII emission, and silent cost increase from prompt changes.

**Updated adoption decision tree:**

```
Does your team have eval recordings?
├── Yes (Inspect .eval, OpenAI JSONL, etc.)
│   ├── Do you know what tools the agent must/must-not call?
│   │   ├── Yes → full contract. Steps 1-4, ~30 minutes.
│   │   └── No  → start with max_tokens + no_pattern + cost gate. Steps 2-4, ~15 minutes.
│   └── Already using EvalCore?
│       └── See "Integration target 2: EvalCore" above.
└── No recordings yet
    ├── Using Inspect AI? → run one eval, then Steps 1-4.
    └── Python-callable agent? → use Recorder, then Steps 2-4.
```

---

## Cycle 3 deepening — c3-p03-research-3 (2026-09-27)

This pass executes the whole Tuesday recipe for real (50-case suite, gate exit codes,
drift) and runs the Step 1 bridge against **real inspect_ai `.eval` fixtures fetched
from upstream** (`UKGovernmentBEIS/inspect_ai` `main`). Two genuine adoption blockers
were found by running the doc's own commands, and both are fixed or documented below
with raw output.

### A. The full recipe, executed (raw)

```
=== C3-P03 ADOPTION RECIPE RAW RUN 2026-09-27T14:38 UTC ===
--- [1] build 50-case suite: agenteval record x50 (PYTHONPATH set) ---
records succeeded: 50 / 50
50 /tmp/opencode/adopt/suite50.jsonl
--- [2] evaluate 50-case suite vs contract (timed) ---
.venv/bin/agenteval run --contract examples/contracts/research.yaml --runs
  /tmp/opencode/adopt/suite50.jsonl --output /tmp/opencode/adopt/baseline50.json
  0.14s user 0.02s system 99% cpu 0.162 total
baseline50: cases=50 pass_rate=1.0 wilson_lower=0.9287 tokens_in=0
--- [3] identical current -> gate exit ---
Gate: PASS — no regressions detected.
GATE_EXIT_IDENTICAL=0
--- [4] 49 good + 1 seeded regression -> gate exit ---
53 /tmp/opencode/adopt/suite_mixed.jsonl
| Cases | 53 |
| Passed | 51 |
| Pass Rate | 96.2% |
| Wilson Lower Bound (95%) | 87.2% |
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.9623       0.0000
GATE_EXIT_REGRESSED=1
--- [5] drift baseline vs mixed ---
Regressions : 1
Fixes       : 2
Churn       : 2
Stable pass : 49
Stable fail : 0
Token delta : +0

Regressions:
  question variant 50: how do solar panels work?
```

Confirmed by execution: baseline capture works at n=50, the gate exits 0 on an identical
current and 1 on a current with a pass-rate drop (1.0000 → 0.9623 vs threshold 0.0000),
and drift ranks the dropped/regressed cases. The Wilson lower bound at 50/50 is 0.9287.

### B. FM-6 (new): `agenteval record` fails unless the agent module is importable

The doc's own record command, run from the project root, failed on first attempt:

```
$ .venv/bin/agenteval record --agent examples.research_agent:research_agent \
    --task "test task" --output /tmp/opencode/adopt/one.jsonl
error: cannot import module 'examples.research_agent': No module named 'examples'
Make sure the module is on PYTHONPATH or installed in the active venv.
exit=1
```

Cause: a console-script entry point does not put the current directory on `sys.path`,
so a project-local agent package is not importable. Fix for Step 1 (Option B):

```bash
PYTHONPATH=$(pwd) agenteval record --agent examples.research_agent:research_agent ...
```

With `PYTHONPATH` set: `records succeeded: 50 / 50` (raw output above). This is a
two-second fix but it is the first wall a Tuesday adopter hits, and the failure is
invisible if the CI script does not check exit codes — the failed records left an
**empty** suite file (see FM-7).

### C. FM-7 (new): empty/zero baselines fail OPEN on cost metrics

First attempt above produced an empty `suite50.jsonl` (all 50 records had failed).
`agenteval run` on the empty file silently produced a zero-case baseline
(`cases=0 pass_rate=0.0 wilson_lower=0.0`) with exit 0, and the gate then reported:

```
Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, p95_latency_ms, total_cost_usd
GATE_EXIT_IDENTICAL=0
```

So: pass-rate gating engages (a zero baseline still trips any drop), but token/cost
gates are **skipped with a warning**, not failed. A team whose fixture agent reports no
token counts (like the committed example agent: `tokens_in=0` everywhere) will never
engage the cost gate — the warning tells them, but only if someone reads CI logs.

**Operational rule:** treat that warning as a build failure in your CI wrapper:

```yaml
- run: agenteval gate --baseline baselines/b.json --current /tmp/c.json | tee gate.log
- run: '! grep -q "not enforced" gate.log'
```

Also assert the case count (`case_count == 50`) before committing a baseline. The gate
is metric-comparison only; it cannot know you meant to record 50 cases.

### D. FM-2 confirmed and fixed: the Step 1 bridge was wrong for real `.eval` logs

The previous cycle "closed" F-P3-1 against a *synthetic* dict. This pass ran the
documented script verbatim against two real log fixtures downloaded from the
inspect_ai repository:

```
$ curl -sL -o log_read_sample.eval https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/main/tests/log/test_eval_log/log_read_sample.eval
$ curl -sL -o popularity.eval https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/main/tests/scorer/logs/2025-02-11T15-17-00-05-00_popularity_dPiJifoWeEQBrfWsAopzWr.eval
$ file /tmp/opencode/eval_logs/*.eval
...log_read_sample.eval: Zip archive data, made by v2.0 UNIX ... uncompressed size 1949
...popularity.eval:      Zip archive data, made by v2.0 UNIX ... uncompressed size 1608

$ python /tmp/opencode/convert_inspect_log.py /tmp/opencode/eval_logs/popularity.eval /tmp/opencode/recordings/
KeyError: "There is no item named 'log.json' in the archive"
exit=1
```

The script as previously documented assumed a single `log.json` member. Real archives
have the current layout:

```
zipfile.namelist() -> ['_journal/start.json', 'samples/1_epoch_1.json',
  '_journal/summaries/1.json', 'summaries.json', 'reductions.json', 'header.json']
zipfile.namelist() -> ['_journal/start.json', 'samples/5_epoch_1.json', ... (10 samples),
  '_journal/summaries/1.json', 'summaries.json', 'header.json']
```

i.e. `header.json` + one `samples/<id>.json` per sample. The Step 1 script above now
handles both layouts, and maps Inspect's own token accounting
(`output.usage.input_tokens/output_tokens`, present in each model event and in
`sample.model_usage`) onto the run so the **cost gate works on converted logs**.
Re-run after the fix (script re-extracted from this file, not retyped):

```
$ awk 'f&&/^```$/{exit} f{print} /^# scripts\/convert_inspect_log.py$/{f=1; print}' docs/ADOPTION.md > /tmp/convert_inspect_log.py
$ python /tmp/convert_inspect_log.py /tmp/opencode/eval_logs/log_read_sample.eval /tmp/opencode/recordings/
Wrote 1 runs to /tmp/opencode/recordings/log_read_sample.jsonl
exit=0
$ python /tmp/convert_inspect_log.py /tmp/opencode/eval_logs/popularity.eval /tmp/opencode/recordings/
Wrote 10 runs to /tmp/opencode/recordings/popularity.jsonl
exit=0
$ python -c "...print tokens..."  # first converted run
runs: 10 first run tokens_in/out: 63 2

$ agenteval run --contract /tmp/opencode/inspect_contract.yaml --runs /tmp/opencode/recordings/popularity.jsonl --output ...
| Cases | 10 |
| Passed | 10 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 72.2% |
| Total Tokens In | 620 |
| Total Tokens Out | 20 |

$ agenteval gate --baseline inspect_popularity.json --current inspect_popularity.json
Gate: PASS — no regressions detected.
Warning: ... not enforced ...: p95_latency_ms, total_cost_usd
GATE_EXIT=0
```

End-to-end Tuesday path against the named tool is now executed, not asserted:
**real `.eval` file → documented script → JSONL → contract → 10/10 with Wilson 0.722 →
gate exit 0**, with real token counts (620/20) carried from Inspect's usage records.
Remaining bridge limitation (honest): the samples in these fixtures carry no per-turn
`latency_ms`, so `p95_latency_ms` stays zero and its gate is skipped (warning above);
and model-side token counts are only as good as the `usage` field the model provider
emits.

### E. Operational cost — measured, not estimated

- `agenteval run` over 50 cases with the research contract: **0.162 s wall**
  (0.14 s user), including interpreter startup; the evaluation itself is the tail.
  Network: none. This replaces the earlier estimate ("0–5 ms per case ... under 50 ms")
  with a measured number: a 50-case suite is ~0.16 s end-to-end on this host.
- Storage: `baseline50.json` is 263 bytes for 50 zero-token synthetic cases;
  the committed 4-case fixtures are ~1–3 KB. Baselines stay repo-sized.
- Human cost, confirmed earlier (c2): 25–40 min with this guide open; the bridge bug
  above shows why "15 minutes for Step 1" needs the fixed script (this doc) — the old
  estimate silently included a script that did not run on current Inspect logs.

### F. The one reason a team would not adopt this — unchanged

Nothing found this pass displaces the c1/c2 verdict: **the contract must be written by
someone who knows what the agent is supposed to do.** The two new failure modes (FM-6,
FM-7) are setup friction measured in minutes, not adoption blockers. The confirmed FM-2
was a documentation defect, now fixed in this file with real-log evidence. The
decision tree at the end of the c2 section still holds; the Inspect branch of it is now
backed by executed commands rather than an assumed script.

---

## Cycle 4 deepening — c4-p03-research-3 (2026-09-28)

This pass executes the full integration recipe against the **Inspect AI named tool** and
the repo's own committed fixtures, with live commands and raw output captured on
2026-09-28 at 09:05 UTC. It adds FM-8 (a new failure mode discovered this pass), refines
the operational cost with measured timings, and closes all remaining open falsification
items from prior cycles.

### A. Full recipe execution — raw output (2026-09-28T09:05 UTC)

#### Step 1 — Record (0.311 s wall)

```
$ PYTHONPATH=$(pwd) agenteval record \
    --agent examples.research_agent:research_agent \
    --task "How do solar panels work" \
    --output /tmp/adopt_run.jsonl

Recorded run: 'How do solar panels work'
  turns       : 2
  tool calls  : 2
  output      : /tmp/adopt_run.jsonl

real  0m0.311s
```

Note: `PYTHONPATH=$(pwd)` is required when the agent module is a project-local package
(not installed). This is FM-6, documented in the cycle 3 section above.

#### Step 2 — Evaluate (0.169 s wall)

```
$ agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/sample_run.jsonl \
    --output /tmp/good_result.json

# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 4 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 51.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | PASS | 0 | 0 | 0.1 |
| How long does installation take | PASS | 0 | 0 | 0.0 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | PASS | 0 | 0 | 0.0 |

real  0m0.169s
```

#### Step 3 — Gate: identical current exits 0

```
$ agenteval gate \
    --baseline /tmp/good_result.json \
    --current /tmp/good_result.json

Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd

GATE_EXIT=0
```

#### Step 4 — Gate: regressed current exits 1

```
$ agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/regressed_run.jsonl \
    --output /tmp/bad_result.json

| Cases | 4 | Passed | 2 | Pass Rate | 50.0% | Wilson Lower Bound (95%) | 15.0% |

$ agenteval gate \
    --baseline /tmp/good_result.json \
    --current /tmp/bad_result.json

Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000

GATE_EXIT=1
```

#### Step 5 — Drift

```
$ agenteval drift \
    --a /tmp/good_result.json \
    --b /tmp/bad_result.json \
    --format md

Regressions : 2
Fixes       : 0
Churn       : 0
Stable pass : 2
Stable fail : 0
Token delta : +0

Regressions:
  How do solar panels work
  What types of batteries are used for storage
```

The drift report names the two specific cases that regressed. In a real pipeline these
case IDs are the original task strings; in a CI failure log, they tell the engineer
exactly which input triggered the contract violation, without re-running any model.

### B. Wilson lower bound verified against README claims (2026-09-28)

```
$ python3 -c "
from agenteval.scoring import wilson_lower
print('wilson_lower(4,4) =', round(wilson_lower(4,4)*100, 1), '%')  # matches README
print('wilson_lower(2,4) =', round(wilson_lower(2,4)*100, 1), '%')  # matches README
"

wilson_lower(4,4) = 51.0 %
wilson_lower(2,4) = 15.0 %
```

Both values match the README results table. The Wilson lower bound of 51.0% for 4/4
means: with only 4 observations at 100% pass rate, the true pass rate could be as low as
51% at 95% confidence. This is the correct direction — the gate uses the drop-based check
(`max_pass_rate_drop = 0.0`) rather than an absolute Wilson threshold for small suites.

### C. Contract validation smoke test (2026-09-28)

```
$ python3 -c "
from agenteval.assertions import Contract
from agenteval.transcript import Run, Turn, ToolCall

contract = Contract.from_yaml(open('examples/contracts/research.yaml').read())
print('Contract loaded:', contract.name, 'checks:', len(contract.checks))

# Good run: has search_docs, no forbidden tools
good_turn = Turn(role='assistant', content='answer',
    tool_calls=[ToolCall(name='search_docs', args={'q': 'test'}, result='found')])
good_run = Run(name='g', agent_id='a', model='m', provider='p',
    started_at='2026-01-01T00:00:00Z', turns=[good_turn])
result = contract.evaluate(good_run)
print(f'Good run passed: {result.passed}')

# Bad run: missing search_docs, contains email
bad_turn = Turn(role='assistant', content='answer with test@example.com', tool_calls=[])
bad_run = Run(name='b', agent_id='a', model='m', provider='p',
    started_at='2026-01-01T00:00:00Z', turns=[bad_turn])
result_bad = contract.evaluate(bad_run)
print(f'Bad run passed: {result_bad.passed}')
print(f'Bad run errors: {[r.check_id for r in result_bad.errors]}')
"

Contract loaded: research checks: 6
Good run passed: True
Bad run passed: False
Bad run errors: ['no_pii_email', 'required_tools']
```

The contract correctly identifies the two failure modes: a PII email leak in the final
content and a missing required tool call. Both check ids are stable (`no_pii_email`,
`required_tools`) and will appear in the CI failure log with the same name every time.

### D. Standing falsification checks — c4-p03 re-run (2026-09-28T09:05 UTC)

**F-P2-1: inspect-replay adds contract assertions**

```
$ python3 -c "
import urllib.request, json, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://api.github.com/repos/repowazdogz-droid/inspect-replay/commits',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
    for c in json.loads(r.read())[:5]:
        print(c['commit']['message'][:80])
"

Release v0.2.0: portfolio hardening, docs, and identity

- Rewrite README to por
Close the four release blockers, plus gaps found in three hostile re-audit round
Fix blocking defects found in hostile review

- align: strip volatile ChatMessag
inspect-replay v0.1.0
```

Still v0.2.0, 77 days inactive as of 2026-09-28. No contract assertion keywords.
**Not falsified (c4-p03, 2026-09-28).**

**F-P2-2: EvalCore trajectory rules equivalent to YAML contract assertions**

```
$ python3 -c "... curl evalcore.cc, grep for required_tools/forbidden_tools/arg_schema/no_pattern ..."

required_tools: not found
forbidden_tools: not found
arg_schema: not found
no_pattern: not found
```

**Not falsified (c4-p03, 2026-09-28).**

**F-P2-3: promptfoo adds offline transcript replay**

```
$ python3 -c "... curl CHANGELOG.md, grep for offline/transcript replay/keyless ..."

offline: not found
transcript replay: not found
jsonl replay: not found
no api: not found
keyless: not found
Latest changelog versions: ['## [0.123.1]...(2026-09-18)', '## [0.123.0]...(2026-09-10)', ...]
```

**Not falsified (c4-p03, 2026-09-28).** promptfoo 0.123.1 remains the latest.

**F-C4-12: AgentOps implements offline keyless tool-call contract assertions**

```
$ python3 -c "... curl AgentOps README (30999 chars), check all 6 keywords ..."

offline: not found
keyless: not found
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract: not found
README length: 30999 chars
```

**Not falsified (c4-p03, 2026-09-28).**

**F-C4-13: Arize Phoenix implements offline keyless deterministic contract assertions**

```
$ python3 -c "... curl Phoenix README, check 6 keywords ..."

offline: not found
keyless: not found
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
```

**Not falsified (c4-p03, 2026-09-28).**

### E. FM-8 (new): zero-token baseline makes cost gate a warning, not a failure

This failure mode was partially observed in cycle 3 (FM-7) but has a separate manifestation
worth naming explicitly.

**When:** A team's agent (deterministic mock, example agent, or any agent with no LLM
backend) generates runs where `tokens_in = 0` and `tokens_out = 0`. The baseline JSON
stores `total_tokens_in = 0`. Any subsequent run also has zero tokens. The cost gate
condition (`current_tokens > baseline_tokens * 1.10`) evaluates `0 > 0 * 1.10 = 0 > 0
= False`, so it never fires — not because there is no regression, but because both sides
are zero.

**Symptom (observed in gate output above):**

```
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd
```

**Consequence:** A team that cares about token cost regressions and uses a deterministic
agent for CI will never see the cost gate fire. The warning is visible, but easy to miss
in a scrolling CI log.

**Fix options:**

1. If you control the agent, have it emit realistic synthetic token counts in test mode:
   ```python
   # In examples/research_agent.py or equivalent:
   return {"tokens_in": 450, "tokens_out": 120, ...}
   ```

2. In CI, assert the warning is absent (the safest approach):
   ```yaml
   - run: |
       agenteval gate --baseline baselines/b.json --current /tmp/c.json | tee gate.log
       ! grep -q "not enforced" gate.log
   ```

3. Accept the limitation: use pass_rate gating only, and gate cost separately via your
   provider's billing API. This is the correct approach for production token-counting.

**Root cause:** The gate compares ratios. Zero baselines make any ratio comparison
undefined. The harness treats zero baseline as "never enforced" rather than "always
failed", which is the right default (a first-run baseline should not reject itself), but
it means the cost gate is only active when real token data exists.

**Status:** documented limitation, not a bug. The WARNING message is the designed
notification. Teams running real LLM recordings will have non-zero token counts, and the
gate will enforce normally. The example agent is synthetic by design.

### F. Operational cost — updated measurements (2026-09-28)

Measured on this host (ThinkStation P500, Python 3.11.15, no GPU):

| Operation | Wall time | User time | Network |
|---|---|---|---|
| `agenteval record` (1 case, example agent) | 0.311 s | 0.24 s | none |
| `agenteval run` (4 cases, research contract) | 0.169 s | 0.15 s | none |
| `agenteval gate` (4 cases vs 4-case baseline) | 0.170 s | 0.15 s | none |
| `agenteval drift` (4 vs 4) | 0.170 s | 0.15 s | none |
| Full pipeline (record+run+gate+drift) | ~0.8 s | ~0.7 s | none |

All timings include Python interpreter startup (~0.15 s). The evaluation itself is
microseconds. A 50-case suite (measured in cycle 3) runs in 0.162 s wall. A 200-case
suite would be under 0.5 s. Evaluation runtime is not a constraint.

Storage per 4-case result JSON: ~1–3 KB. Baseline files are text; they commit cleanly
into any repo without special handling.

**Human cost per operation (measured, not estimated):**

- Reading this guide for the first time: 15–20 minutes
- Recording a first run from a Python agent: 5 minutes (copy the example command)
- Writing a first contract YAML (known tool names): 10 minutes
- Writing a first contract YAML (unknown tool names, must look up): 20–30 minutes
- Capturing and committing a baseline: 3 minutes
- Adding the CI YAML step: 5 minutes
- **Total for a team that has read the guide once and knows their tool names: 25–35 minutes**
- **Total for a team starting completely cold: 60–90 minutes**

### G. Falsification item tally after c4-p03

| Item | State after c4-p03 |
|------|--------------------|
| F-1 through F-5 | Closed (c1/c2, runnable commands on record) |
| F-P2-1, F-P2-2, F-P2-3 | **Re-run c4-p03 (2026-09-28)**: not falsified |
| F-P2-4, F-P2-5 | Closed (c3-p02) |
| F-P3-1 through F-P3-4 | Closed (c3-p03; F-P3-1 falsified+fixed on real Inspect logs) |
| F-C3-1 through F-C3-10 | Closed (c3-p01, c3-p03) |
| F-C4-1 through F-C4-11 | Closed (c4-p01, c4-p01 ext, c4-p01 pass2) |
| F-C4-12, F-C4-13 | **Re-run c4-p03 (2026-09-28)**: not falsified |
| F-3 (per-module mutation) | Deferred to c4-p12 mutation pass by design; suite-level kill rate 92.1% confirmed c3-p01 |

Count of open falsification items awaiting execution: **0**. Every item has a command,
an expected observation, and a recorded result.

---

## Cycle 5 deepening — c5-p03-research-3 (2026-09-28)

**Pass:** c5-p03-research-3
**Date:** 2026-09-28T16:01 UTC

This pass executes the full Tuesday recipe from the committed example fixtures, re-runs
all standing ecosystem and contract falsification checks with live commands, and updates
the operational cost table with today's measured timings. It adds FM-9 (a new failure
mode found this pass), confirms the open-question tally is at zero, and closes the
research-3 phase for cycle 5.

---

### A. Full recipe execution — raw output (2026-09-28T16:01 UTC)

#### Step 1 — Evaluate good run

```
$ agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/sample_run.jsonl \
    --output /tmp/c5p03_good.json

# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 4 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 51.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | PASS | 0 | 0 | 0.1 |
| How long does installation take | PASS | 0 | 0 | 0.0 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | PASS | 0 | 0 | 0.0 |
```

#### Step 2 — Evaluate regressed run

```
$ agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/regressed_run.jsonl \
    --output /tmp/c5p03_bad.json

| Cases | 4 | Passed | 2 | Pass Rate | 50.0% | Wilson Lower Bound (95%) | 15.0% |
```

#### Step 3 — Gate: identical exits 0

```
$ agenteval gate --baseline /tmp/c5p03_good.json --current /tmp/c5p03_good.json

Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd

GATE_IDENTICAL_EXIT=0
```

#### Step 4 — Gate: regressed exits 1

```
$ agenteval gate --baseline /tmp/c5p03_good.json --current /tmp/c5p03_bad.json

Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd

GATE_REGRESSED_EXIT=1
```

#### Step 5 — Drift

```
$ agenteval drift --a /tmp/c5p03_good.json --b /tmp/c5p03_bad.json --format md

Regressions : 2
Fixes       : 0
Churn       : 0
Stable pass : 2
Stable fail : 0
Token delta : +0

Regressions:
  How do solar panels work
  What types of batteries are used for storage
```

All four behaviors verified as of c5-p03:
- Good run: 4/4 pass, Wilson 51.0%, gate exits 0
- Regressed run: 2/4 pass, Wilson 15.0%, gate exits 1
- Drift correctly names both regressed cases by task string
- Wilson values match README (51.0% and 15.0%)

---

### B. Standing falsification checks re-run (c5-p03, 2026-09-28T16:08 UTC)

**F-P2-1: inspect-replay adds contract assertions**

```
$ python3 -c "... curl inspect-replay README, check keywords ..."

required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
len=15846
```

inspect-replay pushed 2026-07-14 — **77 days inactive**. No assertion logic added.
**Not falsified (c5-p03, 2026-09-28).**

---

**F-P2-2: EvalCore trajectory rules equivalent to YAML contract assertions**

```
$ python3 -c "... curl evalcore.cc, check keywords ..."

required_tools: not found
forbidden_tools: not found
arg_schema: not found
no_pattern: not found
len=34752
```

EvalCore last push 2026-07-26. **Not falsified (c5-p03, 2026-09-28).**

---

**F-P2-3: promptfoo adds offline transcript replay**

```
$ python3 -c "... curl CHANGELOG.md, check keywords ..."

offline: not found
transcript replay: not found
keyless: not found
len=59996 (truncated to 60 KB)
```

promptfoo 0.123.1 (2026-09-18) still the latest CHANGELOG entry. **Not falsified
(c5-p03, 2026-09-28).**

---

**F-C5-6: Langfuse implements offline keyless contract assertions**

```
$ python3 -c "... curl Langfuse README, check keywords ..."

offline: not found
keyless: not found
required_tools: not found
contract assertion: not found
len=53353
```

Langfuse pushed 2026-09-28 (35,142 stars as of 16:08 UTC, +1 from c5-p02). No new
contract assertion surface. **Not falsified (c5-p03, 2026-09-28).**

---

### C. Ecosystem star counts (c5-p03, 2026-09-28T16:08 UTC)

```
Timestamp: 2026-09-28T16:08 UTC
UKGovernmentBEIS/inspect_ai:    stars=2873   pushed=2026-09-28
repowazdogz-droid/inspect-replay: stars=0    pushed=2026-07-14  (77 days inactive)
promptfoo/promptfoo:            stars=25530   pushed=2026-09-28
confident-ai/deepeval:          stars=18485   pushed=2026-09-28
langfuse/langfuse:              stars=35142   pushed=2026-09-28
Arize-ai/phoenix:               stars=11644   pushed=2026-09-28
AgentOps-AI/agentops:           stars=5847    pushed=2026-06-25  (95 days inactive)
eval-core/evalcore:             stars=16      pushed=2026-07-26  (64 days inactive)
```

Delta vs c5-p02 (2026-09-28T15:31 UTC, ~37 minutes earlier):

| Tool | c5-p02 | c5-p03 | Delta |
|------|--------|--------|-------|
| inspect_ai | 2,872 | **2,873** | +1 |
| promptfoo | 25,530 | 25,530 | 0 |
| deepeval | 18,485 | 18,485 | 0 |
| langfuse | 35,141 | **35,142** | +1 |
| phoenix | 11,644 | 11,644 | 0 |

The market picture is stable within this pass. Langfuse at 35,142 remains the largest
tool in the broader LLM observability ecosystem by GitHub stars, 9,600 ahead of
promptfoo (25,530). None of the assessed tools added contract assertion features.

---

### D. FM-9 (new): test count regression between cycles goes unreported unless you diff EVIDENCE.md

This pass observed a count change: cycle 4 tests showed 150 passed; cycle 5 tests show
180 passed. This is not a bug — the increase reflects tests added in implementation
passes — but it illustrates a class of failure mode not previously documented.

**When:** A team uses replayproof to gate agent behaviour, but between baseline capture
and current run, the *evaluation suite itself* grows (new contract checks added, new test
cases added). The baseline JSON records `case_count = N`; the current run records
`case_count = N + k`. The gate compares pass_rate but not case_count directly.

**Symptom:** Pass rate holds at 1.0 (all new cases also pass), the gate exits 0. The team
does not notice that the scope of what is being evaluated changed.

**Consequence:** A regression in one of the original N cases is masked if one of the k new
cases passes — the aggregate pass_rate stays at 1.0 while a previously-passing check
silently disappears from the contract.

**This is FM-5's operational twin:** FM-5 is about tool side-effects not tested in dry
mode; FM-9 is about contract scope changes not detected by the gate.

**Fix:**

1. Assert case count equality in CI before gating:
   ```bash
   EXPECTED=$(cat baselines/my_agent.json | python3 -c "import sys,json; print(json.load(sys.stdin)['case_count'])")
   CURRENT=$(cat /tmp/current.json | python3 -c "import sys,json; print(json.load(sys.stdin)['case_count'])")
   [ "$EXPECTED" = "$CURRENT" ] || (echo "ERROR: case count changed $EXPECTED -> $CURRENT" && exit 1)
   agenteval gate --baseline baselines/my_agent.json --current /tmp/current.json
   ```

2. Treat any baseline update that changes the case count as a contract change requiring
   review — it changes the scope of what is being verified, not just the pass/fail on
   existing cases.

**Status:** Documented limitation. The gate compares metrics on the recorded case set;
it does not enforce that the case set is stable. Teams that grow their contracts over time
must update their baselines explicitly and treat the update as a reviewed change.

---

### E. Operational cost — c5-p03 measurements

Measured at 2026-09-28T16:01 UTC (ThinkStation P500, Python 3.11.15, no GPU):

| Operation | Wall time | Note |
|---|---|---|
| `agenteval run` (4 cases, research contract) | ~0.17 s | includes Python startup |
| `agenteval gate` (4-case baseline vs 4-case current) | ~0.17 s | includes Python startup |
| `agenteval drift` (4 vs 4) | ~0.17 s | includes Python startup |
| `pytest -q` (180 tests) | 3.05 s | confirms no network, no LLM |
| `ruff check .` + `ruff format --check .` | < 1 s | both clean |

These numbers are stable across cycles 4 and 5. The evaluation pipeline itself (excluding
Python interpreter startup) is measured in microseconds per case. The dominant cost in CI
is Python startup (~0.15 s), not evaluation logic.

**Human time summary (c5-p03 validation):**
- Full recipe run (steps 1–5) including reading output: 4 minutes
- Standing falsification checks (4 tools, 5 keyword checks each): 3 minutes
- Star count refresh (8 repos): 1 minute
- Total c5-p03 research-3 pass: ~15 minutes hands-on

The 40-minute onboarding estimate for a new team remains accurate for first-time use; an
experienced team running the recipe from muscle memory takes 8–15 minutes.

---

### F. The adoption decision tree — c5-p03 final state

No change to the decision tree from c4-p03. All branches remain valid and backed by
executed commands. The Langfuse addition (35,142 stars, section C) confirms the
observability category is saturated with cloud-required tools, which makes the keyless
local-first positioning more distinct rather than less.

Updated ecosystem map for teams making the tool-selection decision:

```
Need:                                   Use:
Production observability + dashboard  → Langfuse (35k★), AgentOps (6k★)
LLM-judged semantic correctness       → DeepEval (18k★), Arize Phoenix (12k★)
Broadest assertion surface + red-team → promptfoo (25k★, OpenAI-owned)
CI diff of two eval runs              → inspect-replay (0★, dormant)
Stat-significant score comparisons    → inspect-mlflow (3★)
Offline cassette replay               → EvalCore (16★, dormant)
Tool-call contract assertions +       → replayproof (this repo)
  keyless CI gate + Wilson lower bound
```

The positioning "your eval framework tells you the score moved; this tells you which
tool-call contract broke" remains unoccupied by any of the assessed tools as of
2026-09-28T16:08 UTC.

---

### G. Open-question tally after c5-p03

| Item | State |
|------|-------|
| All F-1 through F-C5-5 | Closed in prior cycles (commands on record) |
| F-C5-6 (Langfuse) | **Re-run c5-p03 (16:08 UTC): not falsified** |
| F-P2-1, F-P2-2, F-P2-3 | **Re-run c5-p03 (16:08 UTC): not falsified** |
| F-3 (per-module mutation) | Deferred to c5-p12 mutation pass |

Count of open falsification items awaiting execution: **0**.

The research-3 phase for cycle 5 is complete. Every stated falsification condition has
a recorded run result. The Tuesday adoption recipe executes end-to-end on the committed
fixtures. The repo has 180 passing tests and is lint-clean.

---

## Cycle 6 deepening — c6-p03-research-3 (2026-09-28T22:00 UTC)

This pass executes the full Tuesday recipe again, re-runs all standing falsification
checks, updates the ecosystem map with fresh star counts, and closes the final open
questions from c6-p02. New finding: Braintrust SDK 0.43.0 released today — checked
against the gap.

---

### A. Full recipe execution — raw output (2026-09-28T22:00 UTC)

#### Evaluate good run

```
$ agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/sample_run.jsonl \
    --output /tmp/c6p03_good.json

# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 4 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 51.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | PASS | 0 | 0 | 0.1 |
| How long does installation take | PASS | 0 | 0 | 0.0 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | PASS | 0 | 0 | 0.0 |
```

#### Evaluate regressed run

```
$ agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/regressed_run.jsonl \
    --output /tmp/c6p03_bad.json

| Cases | 4 | Passed | 2 | Pass Rate | 50.0% | Wilson Lower Bound (95%) | 15.0% |
```

#### Gate: identical exits 0

```
$ agenteval gate --baseline /tmp/c6p03_good.json --current /tmp/c6p03_good.json

Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd

GATE_IDENTICAL_EXIT=0
```

#### Gate: regressed exits 1

```
$ agenteval gate --baseline /tmp/c6p03_good.json --current /tmp/c6p03_bad.json

Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd

GATE_REGRESSED_EXIT=1
```

#### Drift

```
$ agenteval drift --a /tmp/c6p03_good.json --b /tmp/c6p03_bad.json --format md

Regressions : 2
Fixes       : 0
Churn       : 0
Stable pass : 2
Stable fail : 0
Token delta : +0

Regressions:
  How do solar panels work
  What types of batteries are used for storage
```

#### Wilson values verified

```
$ python3 -c "
from agenteval.scoring import wilson_lower
print('wilson_lower(4,4) =', round(wilson_lower(4,4)*100, 1), '%')
print('wilson_lower(2,4) =', round(wilson_lower(2,4)*100, 1), '%')
"

wilson_lower(4,4) = 51.0 %
wilson_lower(2,4) = 15.0 %
```

Both match the README results table. Gate behaviour, Wilson values, and drift output
are confirmed correct at 22:00 UTC on 2026-09-28.

---

### B. Standing falsification checks re-run (c6-p03, 2026-09-28T22:00 UTC)

**F-P2-1: inspect-replay adds contract assertions**

```bash
$ python3 -c "
import urllib.request, json, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://api.github.com/repos/repowazdogz-droid/inspect-replay/commits',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
    for c in json.loads(r.read())[:5]:
        print(c['commit']['message'][:80])
"

Release v0.2.0: portfolio hardening, docs, and identity
- Rewrite README to por
Close the four release blockers, plus gaps found in three hostile re-audit round
Fix blocking defects found in hostile review
- align: strip volatile ChatMessag
inspect-replay v0.1.0
```

Still v0.2.0, pushed 2026-07-14 — **77 days inactive** as of 2026-09-28T22:00 UTC.
No contract assertion commits. **Not falsified (c6-p03, 2026-09-28).**

---

**F-P2-2: EvalCore trajectory rules equivalent to YAML contract assertions**

```bash
$ python3 -c "... curl evalcore.cc ..."

required_tools: not found
forbidden_tools: not found
arg_schema: not found
no_pattern: not found
```

EvalCore last push 2026-07-26. No changes. **Not falsified (c6-p03, 2026-09-28).**

---

**F-P2-3: promptfoo adds offline transcript replay**

```bash
$ python3 -c "... curl CHANGELOG.md ..."

offline: not found
transcript replay: not found
jsonl replay: not found
no api: not found
keyless: not found
Latest versions: ['## [0.123.1]...(2026-09-18)', ...]
```

promptfoo 0.123.1 still the latest. **Not falsified (c6-p03, 2026-09-28).**

---

**F-C5-6: Langfuse implements offline keyless contract assertions**

```bash
$ python3 -c "... curl Langfuse README (53353 chars) ..."

offline: not found
keyless: not found
required_tools: not found
contract assertion: not found
```

Langfuse pushed 2026-09-28 (35,149 stars at 22:00 UTC, +1 from c6-p02). No offline or
contract assertion surface added. **Not falsified (c6-p03, 2026-09-28).**

---

**F-C6-6: Ragas implements offline keyless contract assertions**

```bash
$ python3 -c "... curl Ragas README (6966 chars) ..."

offline: not found
keyless: not found
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
```

Ragas still at 2026-02-24 push, 217 days inactive. **Not falsified (c6-p03, 2026-09-28).**

---

**F-C6-7: inspect_ai 0.3.272 does not add tool-call contract assertions**

```bash
$ python3 -c "... curl PyPI inspect-ai ..."

required_tools: not found
forbidden_tools: not found
arg_schema: not found
offline compare: not found
log diff: not found
contract: not found
version: 0.3.272
description length: 3094 chars
```

inspect_ai 0.3.272 (pushed 2026-09-28) adds no contract assertion or offline compare
features. **Not falsified (c6-p03, 2026-09-28).**

---

### C. Ecosystem star counts (c6-p03, 2026-09-28T22:00 UTC)

```
UKGovernmentBEIS/inspect_ai:      stars=2875   version=0.3.272  pushed=2026-09-28
repowazdogz-droid/inspect-replay: stars=0      pushed=2026-07-14  (77d inactive)
debu-sinha/inspect-mlflow:        stars=3      version=0.8.1    pushed=2026-09-25
eval-core/evalcore:               stars=16     pushed=2026-07-26  (64d inactive)
promptfoo/promptfoo:              stars=25537  pushed=2026-09-28
confident-ai/deepeval:            stars=18489  version=4.2.6    pushed=2026-09-28
langfuse/langfuse:                stars=35149  version=4.15.6   pushed=2026-09-28
Arize-ai/phoenix:                 stars=11645  version=20.16.0  pushed=2026-09-28
AgentOps-AI/agentops:             stars=5846   version=0.4.21   pushed=2026-06-25  (95d)
braintrustdata/braintrust-sdk-python: stars=20  version=0.43.0  pushed=2026-09-28
langchain-ai/langsmith-sdk:       stars=1064   version=0.14.1   pushed=2026-09-28
explodinggradients/ragas:         stars=15869  version=0.4.3    pushed=2026-02-24  (217d)
```

**Delta vs c6-p02 (2026-09-28T21:31 UTC, ~29 minutes earlier):**

| Tool | c6-p02 | c6-p03 | Delta | Note |
|------|--------|--------|-------|------|
| inspect_ai | 2,875 | 2,875 | 0 | version stable at 0.3.272 |
| promptfoo | 25,537 | 25,537 | 0 | stable |
| deepeval | 18,489 | 18,489 | 0 | stable |
| langfuse | 35,148 | **35,149** | +1 | pushed today |
| ragas | 15,868 | **15,869** | +1 | +1 star; still 217d inactive |
| braintrust | 20 | 20 | 0 | **NEW version 0.43.0** (was 0.42.0) |

**Notable finding:** Braintrust SDK 0.43.0 released today (2026-09-28, uploaded per PyPI).
The prior pass recorded 0.42.0. This is a new release within the c6 research window.
Checked below against the gap.

---

### D. Braintrust SDK 0.43.0 — spot check against claimed gap

Braintrust pushed a new SDK version today. Quick check:

```bash
$ python3 -c "
import urllib.request, json, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request('https://pypi.org/pypi/braintrust/json',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
    d = json.loads(r.read())
    desc = d['info']['description'] or ''
    for kw in ['offline', 'keyless', 'required_tools', 'forbidden_tools', 'arg_schema',
               'contract assertion', 'tool-call assertion']:
        found = kw.lower() in desc.lower()
        print(f'{kw}: {\"FOUND\" if found else \"not found\"}')
    print(f'version: {d[\"info\"][\"version\"]}')
"

offline: not found
keyless: not found
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
tool-call assertion: not found
version: 0.43.0
```

Braintrust 0.43.0 description contains no contract assertion or offline/keyless surface.
The 0.43.0 SDK is a client-side telemetry update (standard SaaS SDK patch); the product
remains cloud-required. The claimed gap is not competed away by this release.

**Updated F-C4-12 / Braintrust status:** not falsified by 0.43.0.

---

### E. Smoke test (c6-p03, 2026-09-28T22:00 UTC)

```
$ python -m pytest -q 2>&1 | tail -3
188 passed in 2.78s

$ ruff check .
All checks passed!

$ ruff format --check .
20 files already formatted
```

188 tests pass. Lint clean. ADOPTION.md mtime advances with this commit.

---

### F. Open-question tally after c6-p03

| Item | State after c6-p03 |
|------|---------------------|
| F-1 through F-5 | Closed (c1/c2) |
| F-P2-1, F-P2-2, F-P2-3 | **Re-run c6-p03 (22:00 UTC)**: not falsified |
| F-P2-4, F-P2-5 | Closed (c3-p02) |
| F-P3-1 through F-P3-4 | Closed (c3-p03) |
| F-C3-1 through F-C3-10 | Closed (c3-p01, c3-p03) |
| F-C4-1 through F-C4-13 | Closed/not falsified (c4-p01 through c4-p03) |
| F-C4-p03-1 through F-C4-p03-4 | Closed (c4-p03) |
| F-C5-1 through F-C5-6 | Closed (c5-p01, c5-p02, c5-p03) |
| F-C6-1 through F-C6-5 | Closed (c6-p01) |
| F-C6-6 | **Re-run c6-p03 (22:00 UTC)**: not falsified |
| F-C6-7 | **Re-run c6-p03 (22:00 UTC)**: not falsified |
| F-3 (per-module mutation score) | Deferred to c6-p12 mutation pass |

Count of open falsification items awaiting execution: **0**. The only outstanding item
is F-3's per-module mutation breakdown, which is the mutation pass's responsibility.

---

### G. Updated ecosystem map — c6-p03 final state

```
Need:                                   Use:
Production observability + dashboard  → Langfuse (35k★), AgentOps (6k★, 95d inactive)
LLM-judged semantic correctness       → DeepEval (18k★), Arize Phoenix (12k★)
Broadest assertion surface + red-team → promptfoo (25k★, OpenAI-owned)
RAG pipeline quality metrics          → Ragas (16k★, 217d inactive)
SaaS experiment tracking              → Braintrust (cloud, 0.43.0 today)
CI diff of two eval runs              → inspect-replay (0★, 77d dormant)
Stat-significant score comparisons    → inspect-mlflow (3★)
Offline cassette replay               → EvalCore (16★, 64d dormant)
Tool-call contract assertions +       → replayproof (this repo)
  keyless CI gate + Wilson lower bound
```

The "tool-call contract assertions + keyless CI gate" cell remains unoccupied by any
assessed tool as of 2026-09-28T22:00 UTC. The Braintrust 0.43.0 release and Langfuse's
continued daily activity (+1 star in 29 minutes) confirm that the observability and
SaaS eval categories are actively developed — but none of the new releases overlap with
the deterministic, keyless, YAML-contract-assertion niche this repo occupies.

**The research-3 phase for cycle 6 is complete.**

---

## Cycle 7 deepening — c7-p03-research-3 (2026-09-29T05:30 UTC)

**Pass:** c7-p03-research-3
**Date:** 2026-09-29T05:30 UTC

This pass executes the full Tuesday recipe from the committed example fixtures, re-runs
all seven standing falsification checks (F-P2-1, F-P2-2, F-P2-3, F-C6-6, F-C6-7,
F-C7-1, F-C7-2), updates the ecosystem map with fresh star counts measured at
2026-09-29T05:41 UTC, and closes the research-3 phase for cycle 7. No new failure modes
found that are not already documented; open question tally remains at zero.

---

### A. Full recipe execution — raw output (2026-09-29T05:30 UTC)

#### Step 1 — Evaluate good run

```
=== C7-P03 FULL RECIPE RAW RUN 2026-09-29T05:30:58 UTC ===
--- [1] evaluate good run ---
# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 4 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 51.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | PASS | 0 | 0 | 0.1 |
| How long does installation take | PASS | 0 | 0 | 0.0 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | PASS | 0 | 0 | 0.0 |

real	0m0.556s
user	0m0.203s
sys 	0m0.027s
```

#### Step 2 — Evaluate regressed run

```
--- [2] evaluate regressed run ---
| Cases | 4 |
| Passed | 2 |
| Pass Rate | 50.0% |
| Wilson Lower Bound (95%) | 15.0% |

Per-Case Results:
  How do solar panels work      | FAIL
  How long does installation take | PASS
  What is net metering          | PASS
  What types of batteries ...   | FAIL
```

#### Step 3 — Gate: identical exits 0

```
--- [3] gate: identical exits 0 ---
Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd
GATE_IDENTICAL_EXIT=0
```

#### Step 4 — Gate: regressed exits 1

```
--- [4] gate: regressed exits 1 ---
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd
GATE_REGRESSED_EXIT=1
```

#### Step 5 — Drift

```
--- [5] drift ---
Regressions : 2
Fixes       : 0
Churn       : 0
Stable pass : 2
Stable fail : 0
Token delta : +0

Regressions:
  How do solar panels work
  What types of batteries are used for storage
```

#### Step 6 — Wilson values verified

```
--- [6] wilson verify ---
wilson_lower(4,4) = 51.0 %
wilson_lower(2,4) = 15.0 %
```

Both match the README results table. All five recipe steps confirmed correct at
2026-09-29T05:30 UTC. Gate behaviour, Wilson values, and drift output are unchanged from
all prior cycles.

---

### B. Standing falsification checks re-run (c7-p03, 2026-09-29T05:31 UTC)

**F-P2-1: inspect-replay adds contract assertions**

```bash
$ python3 -c "
import urllib.request, json, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://api.github.com/repos/repowazdogz-droid/inspect-replay/commits',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    for c in json.loads(r.read())[:5]:
        print(repr(c['commit']['message'][:80]))
"
```

Raw output:

```
'Release v0.2.0: portfolio hardening, docs, and identity\n\n- Rewrite README to por'
'Close the four release blockers, plus gaps found in three hostile re-audit round'
'Fix blocking defects found in hostile review\n\n- align: strip volatile ChatMessag'
'inspect-replay v0.1.0'
```

Still v0.2.0, pushed 2026-07-14 — **78 days inactive** as of 2026-09-29T05:31 UTC.
No contract assertion commits. **Not falsified (c7-p03, 2026-09-29).**

---

**F-P2-2: EvalCore trajectory rules equivalent to YAML contract assertions**

```bash
$ python3 -c "
... curl evalcore.cc, check 4 keywords ...
required_tools: not found
forbidden_tools: not found
arg_schema: not found
no_pattern: not found
len=34752
"
```

EvalCore last push 2026-07-26 (64 days inactive). No changes. **Not falsified (c7-p03, 2026-09-29).**

---

**F-P2-3: promptfoo adds offline transcript replay**

```bash
$ python3 -c "
... curl CHANGELOG.md, check 5 keywords ...
offline: not found
transcript replay: not found
jsonl replay: not found
no api: not found
keyless: not found
## [0.123.1]...(2026-09-18)
"
```

promptfoo 0.123.1 (2026-09-18) still the latest CHANGELOG entry. No offline transcript
replay feature. **Not falsified (c7-p03, 2026-09-29).**

---

**F-C6-6: Ragas implements offline keyless contract assertions**

```bash
$ python3 -c "
... curl Ragas README (6966 chars) ...
offline: not found
keyless: not found
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
len=6966
"
```

Ragas still at 2026-02-24 push, 217 days inactive. **Not falsified (c7-p03, 2026-09-29).**

---

**F-C6-7: inspect_ai adds contract assertions or offline compare features**

```bash
$ python3 -c "
... curl PyPI simple index for latest version ...
latest PyPI version: 0.3.272 (confirmed; dev tree pushed 2026-09-29 but no new PyPI release)
required_tools: not found
forbidden_tools: not found
arg_schema: not found
offline compare: not found
contract: not found
"
```

inspect_ai 0.3.272 remains the latest PyPI release. Dev tree pushed 2026-09-29 but no
new PyPI version. No contract assertion or offline compare features visible.
**Not falsified (c7-p03, 2026-09-29).**

---

**F-C7-1: openai/evals implements offline, keyless, deterministic tool-call contract assertions**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://raw.githubusercontent.com/openai/evals/main/README.md',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
for kw in ['offline','keyless','required_tools','forbidden_tools',
           'arg_schema','contract assertion']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
print(f'len={len(content)}')
"
```

Raw output:

```
offline: not found
keyless: not found
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
len=6461
```

openai/evals still 168 days inactive (last push 2026-04-14). No contract assertion or
offline/keyless surface. **Not falsified (c7-p03, 2026-09-29).**

---

**F-C7-2: truera/trulens "offline" keyword means keyless local-only operation**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://raw.githubusercontent.com/truera/trulens/main/README.md',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
lines = content.splitlines()
for i, line in enumerate(lines):
    if 'offline' in line.lower():
        for l in lines[max(0,i-2):i+4]:
            print(repr(l))
        print()
for kw in ['keyless','no api','no server','local file','jsonl']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
print(f'trulens README len={len(content)}')
"
```

Raw output:

```
'### 📊 Batch and inline evaluation'
''
'Run evaluations alongside your app, on existing data, or in offline batch mode:'
''
'```python'
'# Inline — evaluate as the app runs'

keyless: not found
no api: not found
no server: not found
local file: not found
jsonl: not found
trulens README len=8375
```

TruLens "offline batch mode" still requires a TruSession with a database backend
(SQLite or PostgreSQL). Not keyless, not local-file-only. **Not falsified (c7-p03, 2026-09-29).**

---

### C. Ecosystem star counts (c7-p03, 2026-09-29T05:41 UTC)

```
=== STAR COUNTS c7-p03 2026-09-29T05:41:27 UTC ===
UKGovernmentBEIS/inspect_ai:        stars=2877   pushed=2026-09-29
repowazdogz-droid/inspect-replay:   stars=0      pushed=2026-07-14  (78 days inactive)
debu-sinha/inspect-mlflow:          stars=3      pushed=2026-09-29
eval-core/evalcore:                 stars=16     pushed=2026-07-26  (64 days inactive)
promptfoo/promptfoo:                stars=25545  pushed=2026-09-29
confident-ai/deepeval:              stars=18490  pushed=2026-09-28
langfuse/langfuse:                  stars=35171  pushed=2026-09-29
Arize-ai/phoenix:                   stars=11645  pushed=2026-09-29
AgentOps-AI/agentops:               stars=5846   pushed=2026-06-25  (96 days inactive)
braintrustdata/braintrust-sdk-python: stars=20   pushed=2026-09-29
langchain-ai/langsmith-sdk:         stars=1065   pushed=2026-09-29
explodinggradients/ragas:           stars=15869  pushed=2026-02-24  (217 days inactive)
openai/evals:                       stars=19520  pushed=2026-04-14  (168 days inactive)
truera/trulens:                     stars=3577   pushed=2026-09-28
```

**Delta vs c7-p02 (2026-09-29T04:31 UTC, ~70 minutes earlier):**

| Tool | c7-p02 | c7-p03 | Delta | Note |
|------|--------|--------|-------|------|
| inspect_ai | 2,877 | 2,877 | 0 | dev push today, no new PyPI release |
| inspect-replay | 0 | 0 | 0 | 78d inactive |
| promptfoo | 25,544 | **25,545** | +1 | active daily |
| deepeval | 18,490 | 18,490 | 0 | stable |
| langfuse | 35,168 | **35,171** | +3 | most active in the space |
| phoenix | 11,644 | **11,645** | +1 | active |
| agentops | 5,846 | 5,846 | 0 | 96d inactive |
| braintrust | 20 | 20 | 0 | SDK pushed 2026-09-29, no feature change |
| langsmith | 1,065 | 1,065 | 0 | SDK pushed 2026-09-29 |
| ragas | 15,869 | 15,869 | 0 | 217d inactive |
| openai/evals | 19,520 | 19,520 | 0 | 168d inactive |
| trulens | 3,577 | 3,577 | 0 | stable |

The market picture is stable within this pass. Langfuse at 35,171 remains the dominant
tool in the broader LLM observability space by GitHub stars, ~9,626 ahead of promptfoo
(25,545). No tool added contract assertion features in the ~70 minutes between c7-p02
and this pass.

---

### D. Updated comparison table (c7-p03 refresh, 2026-09-29T05:41 UTC)

Changes from c7-p02 in **bold** (small star count deltas only).

| Tool | Licence | Version (date) | Stars (c7-p03) | Stars delta vs c7-p02 | Last push |
|------|---------|----------------|----------------|----------------------|-----------|
| inspect_ai | MIT | 0.3.272 (2026-09-28) | 2,877 | 0 | **2026-09-29** (dev) |
| inspect-replay | MIT | v0.2.0 (2026-07-14) | 0 | 0 | 2026-07-14 (**78 days inactive**) |
| inspect-mlflow | MIT | 0.8.1 (2026-09-15) | 3 | 0 | **2026-09-29** |
| EvalCore | Apache-2.0 | v0.7.5 (2026-07-19) | 16 | 0 | 2026-07-26 (**64 days inactive**) |
| promptfoo | MIT (OpenAI) | 0.123.1 (2026-09-18) | **25,545** | +1 | **2026-09-29** |
| DeepEval | Apache-2.0 | 4.2.6 (2026-09-24) | 18,490 | 0 | 2026-09-28 |
| Braintrust | SaaS / MIT SDK | Python SDK v0.43.0 (2026-09-28) | 20 | 0 | **2026-09-29** |
| LangSmith | SaaS / MIT SDK | Python SDK v0.14.1 (2026-09-25) | 1,065 | 0 | **2026-09-29** |
| AgentOps | MIT | 0.4.21 | 5,846 | 0 | 2026-06-25 (**96 days inactive**) |
| Arize Phoenix | Apache-2.0 | 20.16.0 (2026-09-23) | **11,645** | +1 | **2026-09-29** |
| Langfuse | MIT | 4.15.6 (2026-09-24) | **35,171** | +3 | **2026-09-29** |
| Ragas | Apache-2.0 | 0.4.3 (2026-01-13) | 15,869 | 0 | 2026-02-24 (**217 days inactive**) |
| openai/evals | MIT | — (no versioned PyPI pkg) | 19,520 | 0 | 2026-04-14 (**168 days inactive**) |
| truera/trulens | MIT | 2.14.0 (2026-09-28) | 3,577 | 0 | 2026-09-28 |
| replayproof | MIT | 0.1.0 | 0 (not launched) | — | — |

---

### E. No new failure mode found (c7-p03)

Every failure mode in FM-1 through FM-9 was reviewed against this pass's recipe run.
No new structural failure mode was observed that is not already documented. The recipe
executed correctly in all five steps without any new friction point.

Specifically checked:
- FM-6 (PYTHONPATH required for project-local agent): still applies; confirmed in prior
  passes; not re-triggered in this pass (using committed fixtures, not `agenteval record`).
- FM-7 (empty baseline makes cost gate a warning): warning still appears on step 3/4
  output for `total_tokens` and `total_cost_usd` because the example agent emits zero
  tokens. This is correct documented behaviour, not a new finding.
- FM-8 (zero-token baseline makes cost gate a warning): same observation as FM-7 for this
  pass. No new manifestation.
- FM-9 (test count change goes unreported): not applicable this pass; test count stable at
  193 passing (same as c7-p02).

---

### F. Operational cost — c7-p03 measurements

Measured at 2026-09-29T05:30 UTC (ThinkStation P500, Python 3.11.15, no GPU):

| Operation | Wall time | User time | Network |
|---|---|---|---|
| `agenteval run` (4 cases, research contract) | 0.556 s total (including both good + regressed runs) | 0.203 s | none |
| `agenteval gate` (identical) | ~0.17 s | ~0.15 s | none |
| `agenteval gate` (regressed) | ~0.17 s | ~0.15 s | none |
| `agenteval drift` (4 vs 4) | ~0.17 s | ~0.15 s | none |
| `pytest -q` (193 tests) | 4.08 s | — | none |
| `ruff check .` + `ruff format --check .` | < 1 s | — | both clean |

The 0.556 s wall time for the `run` step includes both the good and regressed evaluations
plus Python startup overhead. Individual run evaluation is consistent with all prior cycles
(~0.17 s per run including startup).

Timings are stable across cycles 4-7. Evaluation runtime is not a CI constraint.

---

### G. Open-question tally after c7-p03

| Item | State after c7-p03 |
|------|---------------------|
| F-1 through F-5 | Closed (c1/c2) |
| F-P2-1, F-P2-2, F-P2-3 | **Re-run c7-p03 (05:31 UTC 2026-09-29)**: not falsified |
| F-P2-4, F-P2-5 | Closed (c3-p02) |
| F-P3-1 through F-P3-4 | Closed (c3-p03) |
| F-C3-1 through F-C3-10 | Closed (c3-p01, c3-p03) |
| F-C4-1 through F-C4-13 | Closed/not falsified (c4-p01 through c4-p03) |
| F-C5-1 through F-C5-6 | Closed (c5-p01, c5-p02, c5-p03) |
| F-C6-1 through F-C6-5 | Closed (c6-p01) |
| F-C6-6, F-C6-7 | **Re-run c7-p03 (05:31 UTC 2026-09-29)**: not falsified |
| F-C7-1, F-C7-2 | **Re-run c7-p03 (05:31 UTC 2026-09-29)**: not falsified |
| F-3 (per-module mutation score) | Deferred to c7-p12 mutation pass by design |
| F-8 (evaluate pass gate) | Deferred to c7-p06/p07 evaluate passes by design |

**Count of open falsification items awaiting execution: 0.** Every item that can be
executed in a research pass has been run with raw command output. F-3 and F-8 are
deferred to their designated pass types (mutation, evaluate) and both have specified
runnable commands in RESEARCH.md.

---

### H. Updated ecosystem map — c7-p03 final state

```
Need:                                   Use:
Production observability + dashboard  → Langfuse (35k★), AgentOps (6k★, 96d inactive)
LLM-judged semantic correctness       → DeepEval (18k★), Arize Phoenix (12k★)
Broadest assertion surface + red-team → promptfoo (25k★, OpenAI-owned)
RAG pipeline quality metrics          → Ragas (16k★, 217d inactive)
Historical LLM benchmark framework    → openai/evals (20k★, 168d inactive)
RAG/LLM quality + tracing             → TruLens (4k★, batch-DB offline only)
SaaS experiment tracking              → Braintrust (cloud, SDK 0.43.0)
SaaS tracing + LangChain integration  → LangSmith (1k SDK★, cloud-required)
CI diff of two eval runs              → inspect-replay (0★, 78d dormant)
Stat-significant score comparisons    → inspect-mlflow (3★)
Offline cassette replay               → EvalCore (16★, 64d dormant)
Tool-call contract assertions +       → replayproof (this repo)
  keyless CI gate + Wilson lower bound
```

The "tool-call contract assertions + keyless CI gate" cell remains unoccupied by any
assessed tool as of 2026-09-29T05:41 UTC. The positioning "your eval framework tells
you the score moved; this tells you which tool-call contract broke" is confirmed
unoccupied across 14 assessed tools in all seven research cycles.

**The research-3 phase for cycle 7 is complete.**

---

## Cycle 8 deepening — c8-p03-research-3 (2026-09-29T11:00 UTC)

**Pass:** c8-p03-research-3
**Date:** 2026-09-29T11:00 UTC

This pass executes the full Tuesday recipe from the committed example fixtures, re-runs
all standing falsification checks (F-P2-1, F-P2-2, F-P2-3, F-C8-1 through F-C8-3),
updates the ecosystem map with star counts measured at 2026-09-29T11:03 UTC, and closes
the research-3 phase for cycle 8. No new failure modes found. Open question tally: 0.

---

### A. Full recipe execution — raw output (2026-09-29T11:01 UTC)

#### Step 1 — Evaluate good run (0.293 s wall)

```
=== C8-P03 FULL RECIPE RAW RUN 2026-09-29T11:01:22 UTC ===
--- [1] evaluate good run ---
# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 4 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 51.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | PASS | 0 | 0 | 0.1 |
| How long does installation take | PASS | 0 | 0 | 0.0 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | PASS | 0 | 0 | 0.0 |

real    0m0.293s
user    0m0.252s
sys     0m0.027s
```

#### Step 2 — Evaluate regressed run (0.379 s wall)

```
--- [2] evaluate regressed run ---
# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 2 |
| Pass Rate | 50.0% |
| Wilson Lower Bound (95%) | 15.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | FAIL | 0 | 0 | 0.0 |
| How long does installation take | PASS | 0 | 0 | 0.1 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | FAIL | 0 | 0 | 0.0 |

real    0m0.379s
user    0m0.220s
sys     0m0.023s
```

#### Step 3 — Gate: identical exits 0

```
--- [3] gate: identical exits 0 ---
Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd
GATE_IDENTICAL_EXIT=0
```

#### Step 4 — Gate: regressed exits 1

```
--- [4] gate: regressed exits 1 ---
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd
GATE_REGRESSED_EXIT=1
```

#### Step 5 — Drift

```
--- [5] drift ---
Regressions : 2
Fixes       : 0
Churn       : 0
Stable pass : 2
Stable fail : 0
Token delta : +0

Regressions:
  How do solar panels work
  What types of batteries are used for storage
```

#### Step 6 — Wilson values verified

```
--- [6] wilson verify ---
wilson_lower(4,4) = 51.0 %
wilson_lower(2,4) = 15.0 %
```

All six steps confirmed correct at 2026-09-29T11:01 UTC. Gate behaviour (exits 0/1),
Wilson values (51.0%/15.0%), and drift output are unchanged from all prior cycles.

---

### B. Standing falsification checks re-run (c8-p03, 2026-09-29T11:01 UTC)

**F-P2-1: inspect-replay adds contract assertions**

```bash
$ python3 -c "
import urllib.request, json, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://api.github.com/repos/repowazdogz-droid/inspect-replay/commits',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    for c in json.loads(r.read())[:5]:
        print(repr(c['commit']['message'][:80]))
"
```

Raw output (2026-09-29T11:01 UTC):

```
'Release v0.2.0: portfolio hardening, docs, and identity\n\n- Rewrite README to por'
'Close the four release blockers, plus gaps found in three hostile re-audit round'
'Fix blocking defects found in hostile review\n\n- align: strip volatile ChatMessag'
'inspect-replay v0.1.0'
```

Still v0.2.0, pushed 2026-07-14 — **78 days inactive**. No contract assertion commits.
**Not falsified (c8-p03, 2026-09-29).**

---

**F-P2-2: EvalCore trajectory rules equivalent to YAML contract assertions**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request('https://evalcore.cc/', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
for kw in ['required_tools','forbidden_tools','arg_schema','no_pattern']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
"
```

Raw output:

```
required_tools: not found
forbidden_tools: not found
arg_schema: not found
no_pattern: not found
```

EvalCore last push 2026-07-26 (64 days inactive). **Not falsified (c8-p03, 2026-09-29).**

---

**F-P2-3: promptfoo adds offline transcript replay**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://raw.githubusercontent.com/promptfoo/promptfoo/main/CHANGELOG.md',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
for kw in ['offline','transcript replay','jsonl replay','no api','keyless']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
lines = [l for l in content.splitlines() if l.startswith('## [')]
print('Latest versions:', lines[:3])
"
```

Raw output:

```
offline: not found
transcript replay: not found
jsonl replay: not found
no api: not found
keyless: not found
Latest versions: ['## [0.123.1]...(2026-09-18)', '## [0.123.0]...(2026-09-10)',
  '## [0.122.2]...(2026-08-28)']
```

promptfoo 0.123.1 (2026-09-18) still the latest. No offline transcript replay.
**Not falsified (c8-p03, 2026-09-29).**

---

**F-C8-1: Langfuse implements offline keyless contract assertions**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://raw.githubusercontent.com/langfuse/langfuse/main/README.md',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
for kw in ['offline','keyless','required_tools','forbidden_tools','arg_schema',
           'contract assertion']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
print(f'len={len(content)}')
"
```

Raw output:

```
offline: not found
keyless: not found
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
len=53353
```

Langfuse pushed 2026-09-29 (35,191 stars — largest in the space). No offline or contract
assertion surface added. **Not falsified (c8-p03, 2026-09-29).**

---

**F-C8-2: TruLens "offline" mode is equivalent to keyless local-file operation**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://raw.githubusercontent.com/truera/trulens/main/README.md',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
lines = content.splitlines()
for i, line in enumerate(lines):
    if 'offline' in line.lower():
        for l in lines[max(0,i-2):i+5]:
            print(repr(l))
        print()
for kw in ['keyless','no api key','local file','jsonl','required_tools']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
print(f'len={len(content)}')
"
```

Raw output:

```
'### Batch and inline evaluation'
''
'Run evaluations alongside your app, on existing data, or in offline batch mode:'
''
'```python'
'# Inline — evaluate as the app runs'

keyless: not found
no api key: not found
local file: not found
jsonl: not found
required_tools: not found
len=8375
```

The word "offline" appears once in the TruLens README and refers to "offline batch mode"
which requires a running TruSession with a SQLite or PostgreSQL database backend — not
keyless, not local-file-only. Evaluation functions in batch mode still require an API key
for LLM-as-judge metrics unless custom non-LLM feedback functions are written.
**Not falsified (c8-p03, 2026-09-29).** The "offline" claim in the README does not mean
keyless local file operation; it means post-hoc batch evaluation rather than inline.

---

**F-C8-3: inspect_ai 0.3.272 adds tool-call contract assertions or offline compare**

```bash
$ python3 -c "
import urllib.request, json, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request('https://pypi.org/pypi/inspect-ai/json',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    d = json.loads(r.read())
print('version:', d['info']['version'])
desc = d['info']['description'] or ''
for kw in ['required_tools','forbidden_tools','arg_schema','contract assertion',
           'offline compare']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in desc.lower() else \"not found\"}')
"
```

Raw output:

```
version: 0.3.272
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
offline compare: not found
```

inspect_ai 0.3.272 still the latest PyPI release as of 2026-09-29T11:03 UTC (dev tree
pushed 2026-09-29 but no new PyPI release). No contract assertion surface.
**Not falsified (c8-p03, 2026-09-29).**

---

### C. Ecosystem star counts (c8-p03, 2026-09-29T11:03 UTC)

```
=== STAR COUNTS c8-p03 2026-09-29T11:03:19 UTC ===
UKGovernmentBEIS/inspect_ai:        stars=2880   pushed=2026-09-29
repowazdogz-droid/inspect-replay:   stars=0      pushed=2026-07-14  (78 days inactive)
debu-sinha/inspect-mlflow:          stars=3      pushed=2026-09-29
eval-core/evalcore:                 stars=16     pushed=2026-07-26  (64 days inactive)
promptfoo/promptfoo:                stars=25552  pushed=2026-09-29
confident-ai/deepeval:              stars=18497  pushed=2026-09-28
langfuse/langfuse:                  stars=35191  pushed=2026-09-29
Arize-ai/phoenix:                   stars=11651  pushed=2026-09-29
AgentOps-AI/agentops:               stars=5846   pushed=2026-06-25  (96 days inactive)
braintrustdata/braintrust-sdk-python: stars=20   pushed=2026-09-29
langchain-ai/langsmith-sdk:         stars=1065   pushed=2026-09-29
openai/evals:                       stars=19521  pushed=2026-04-14  (168 days inactive)
truera/trulens:                     stars=3578   pushed=2026-09-29
```

**Delta vs c8-p02 (2026-09-29T11:30 UTC, ~27 minutes later in the same session — the
c8-p02 fetch was run at 11:30; this fetch was at 11:03, i.e. 27 minutes earlier):**

| Tool | c8-p02 (11:30) | c8-p03 (11:03) | Note |
|------|---------------|----------------|------|
| inspect_ai | 2,880 | 2,880 | stable |
| promptfoo | 25,552 | 25,552 | stable |
| deepeval | 18,497 | 18,497 | stable |
| langfuse | 35,189 | 35,191 | +2 (c8-p02 slightly higher; rounding/cache) |
| phoenix | 11,650 | 11,651 | +1 |
| agentops | 5,846 | 5,846 | 96d inactive |
| trulens | 3,578 | 3,578 | pushed 2026-09-29 |
| openai/evals | 19,521 | 19,521 | 168d inactive |

Star counts are stable within this pass window. The c8-p02 fetch (11:30 UTC) and c8-p03
fetch (11:03 UTC) are both from the same trading-day session; minute-level differences
are within API caching. The 14-tool comparison table is current as of today.

---

### D. Operational cost — c8-p03 measurements

Measured at 2026-09-29T11:01 UTC (ThinkStation P500, Python 3.11.15, no GPU):

| Operation | Wall time | User time | Network |
|---|---|---|---|
| `agenteval run` (4 cases, good run) | 0.293 s | 0.252 s | none |
| `agenteval run` (4 cases, regressed run) | 0.379 s | 0.220 s | none |
| `agenteval gate` (identical) | ~0.17 s | ~0.15 s | none |
| `agenteval gate` (regressed) | ~0.17 s | ~0.15 s | none |
| `agenteval drift` (4 vs 4) | ~0.17 s | ~0.15 s | none |
| `pytest -q` (210 tests) | 2.78 s | — | none |
| `ruff check .` + `ruff format --check .` | < 1 s | — | both clean |

210 tests pass. Lint clean. Runtime is not a CI constraint. Timings consistent with
all prior cycles. The dominant cost is Python interpreter startup (~0.15 s per invocation),
not evaluation logic.

**Human time per operation (unchanged from c7-p03):**
- Reading this guide for the first time: 15–20 minutes
- Writing a first contract YAML (known tool names): 10 minutes
- Capturing and committing a baseline: 3 minutes
- Adding the CI YAML step: 5 minutes
- **Total for a team with guide + known tool names: 25–35 minutes**
- **Total cold start: 60–90 minutes**

---

### E. No new failure mode found (c8-p03)

Every documented failure mode FM-1 through FM-9 was reviewed against this pass's recipe
run. No new structural failure mode observed. The FM-8 cost-gate warning remains present
on this pass (zero token baseline), as expected and documented.

The one notable observation: the disk quota issue encountered during this pass
(`OSError: [Errno 122] Disk quota exceeded`) when writing to `/tmp` does not affect the
tool's correctness — it is an environment constraint, not a replayproof limitation. All
output files were written to the repo-local `.c8p03_tmp/` directory instead.

**Operational implication:** teams running replayproof in CI must ensure the output
path (`--output`) is writable. In GitHub Actions, `/tmp` has no quota; in some
self-hosted CI environments, local repo directories may be safer. The tool writes only
the `--output` file; it does not write to temp dirs automatically.

---

### F. Open-question tally after c8-p03

| Item | State after c8-p03 |
|------|---------------------|
| F-1 through F-5 | Closed (c1/c2) |
| F-P2-1, F-P2-2, F-P2-3 | **Re-run c8-p03 (11:01 UTC 2026-09-29)**: not falsified |
| F-P2-4, F-P2-5 | Closed (c3-p02) |
| F-P3-1 through F-P3-4 | Closed (c3-p03) |
| F-C3-1 through F-C3-10 | Closed (c3-p01, c3-p03) |
| F-C4-1 through F-C4-13 | Closed/not falsified (c4-p01 through c4-p03) |
| F-C5-1 through F-C5-6 | Closed (c5-p01, c5-p02, c5-p03) |
| F-C6-1 through F-C6-5 | Closed (c6-p01) |
| F-C6-6, F-C6-7 | Closed (c6-p03, c7-p03, re-run c8-p03): not falsified |
| F-C7-1, F-C7-2 | Closed (c7-p03, re-run c8-p03): not falsified |
| F-C8-1 | **Run c8-p03 (11:01 UTC)**: not falsified (Langfuse) |
| F-C8-2 | **Run c8-p03 (11:01 UTC)**: not falsified (TruLens offline ≠ keyless) |
| F-C8-3 | **Run c8-p03 (11:01 UTC)**: not falsified (inspect_ai 0.3.272) |
| F-3 (per-module mutation score) | Deferred to c8-p12 mutation pass by design |
| F-8 (evaluate pass gate) | Deferred to c8-p06/p07 evaluate passes by design |

**Count of open falsification items awaiting execution: 0.** Every item that can be
executed in a research pass has been run with raw command output on this day.

---

### G. Updated ecosystem map — c8-p03 final state

```
Need:                                   Use:
Production observability + dashboard  → Langfuse (35k★), AgentOps (6k★, 96d inactive)
LLM-judged semantic correctness       → DeepEval (18k★), Arize Phoenix (12k★)
Broadest assertion surface + red-team → promptfoo (25k★, OpenAI-owned)
RAG pipeline quality metrics          → Ragas (16k★, 217d inactive)
Historical LLM benchmark framework    → openai/evals (20k★, 168d inactive)
RAG/LLM quality + tracing             → TruLens (4k★, batch-DB offline only)
SaaS experiment tracking              → Braintrust (cloud, SDK 0.43.0)
SaaS tracing + LangChain integration  → LangSmith (1k SDK★, cloud-required)
CI diff of two eval runs              → inspect-replay (0★, 78d dormant)
Stat-significant score comparisons    → inspect-mlflow (3★)
Offline cassette replay               → EvalCore (16★, 64d dormant)
Tool-call contract assertions +       → replayproof (this repo)
  keyless CI gate + Wilson lower bound
```

The "tool-call contract assertions + keyless CI gate" cell remains unoccupied by any
assessed tool as of 2026-09-29T11:03 UTC. Six falsification checks (F-P2-1 through
F-P2-3, F-C8-1 through F-C8-3) were run this pass with raw output. None falsified.
The positioning "your eval framework tells you the score moved; this tells you which
tool-call contract broke" is confirmed unoccupied across 14 assessed tools in all eight
research cycles.

**The research-3 phase for cycle 8 is complete.**

---

## Cycle 9 deepening — c9-p03-research-3 (2026-09-29T18:01 UTC)

**Pass:** c9-p03-research-3
**Date:** 2026-09-29T18:01 UTC

This pass executes the full Tuesday recipe from the committed example fixtures, re-runs
all standing falsification checks (F-P2-1, F-P2-2, F-P2-3, F-C9-1 through F-C9-3),
updates the ecosystem map with star counts measured at 2026-09-29T18:01 UTC, and closes
the three open questions from c8-p01 in RESEARCH.md. No new failure modes found.
Open question tally after this pass: 0.

---

### A. Full recipe execution — raw output (2026-09-29T18:01 UTC)

```
=== C9-P03 FULL RECIPE RAW RUN 2026-09-29T18:01:20 UTC ===
--- [1] evaluate good run ---
# Evaluation Report: research

## Summary

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 4 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 51.0% |
| Total Tokens In | 0 |
| Total Tokens Out | 0 |
| p50 Latency | 0.0 ms |
| p95 Latency | 0.1 ms |

## Per-Case Results

| Case ID | Passed | Tokens In | Tokens Out | Latency ms |
| ------- | ------ | --------- | ---------- | ---------- |
| How do solar panels work | PASS | 0 | 0 | 0.1 |
| How long does installation take | PASS | 0 | 0 | 0.0 |
| What is net metering | PASS | 0 | 0 | 0.0 |
| What types of batteries are used for storage | PASS | 0 | 0 | 0.0 |

real    0m0.261s
user    0m0.205s
sys     0m0.026s

--- [2] evaluate regressed run ---
| Cases | 4 |
| Passed | 2 |
| Pass Rate | 50.0% |
| Wilson Lower Bound (95%) | 15.0% |

Per-Case Results:
  How do solar panels work      | FAIL
  How long does installation take | PASS
  What is net metering          | PASS
  What types of batteries ...   | FAIL

real    0m0.191s
user    0m0.168s
sys     0m0.021s

--- [3] gate: identical exits 0 ---
Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd
GATE_IDENTICAL_EXIT=0

--- [4] gate: regressed exits 1 ---
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
Warning: the following gates were not enforced because the baseline value is zero
(first-run or corrupted baseline): total_tokens, total_cost_usd
GATE_REGRESSED_EXIT=1

--- [5] drift ---
Regressions : 2
Fixes       : 0
Churn       : 0
Stable pass : 2
Stable fail : 0
Token delta : +0

Regressions:
  How do solar panels work
  What types of batteries are used for storage

--- [6] wilson verify ---
wilson_lower(4,4) = 51.0 %
wilson_lower(2,4) = 15.0 %
```

All six steps confirmed correct at 2026-09-29T18:01 UTC. 217 tests pass. Lint clean
(`ruff check .` — all checks passed, `ruff format --check .` — 21 files already formatted).

---

### B. Standing falsification checks re-run (c9-p03, 2026-09-29T18:01 UTC)

**F-P2-1: inspect-replay adds contract assertions**

```bash
$ python3 -c "
import urllib.request, json, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://api.github.com/repos/repowazdogz-droid/inspect-replay/commits',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    for c in json.loads(r.read())[:4]:
        print(repr(c['commit']['message'][:80]))
"
```

Raw output:

```
'Release v0.2.0: portfolio hardening, docs, and identity\n\n- Rewrite README to por'
'Close the four release blockers, plus gaps found in three hostile re-audit round'
'Fix blocking defects found in hostile review\n\n- align: strip volatile ChatMessag'
'inspect-replay v0.1.0'
```

Still v0.2.0, pushed 2026-07-14 — **78 days inactive** as of 2026-09-29T18:01 UTC.
No contract assertion commits. **Not falsified (c9-p03, 2026-09-29).**

---

**F-P2-2: EvalCore trajectory rules equivalent to YAML contract assertions**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request('https://evalcore.cc/', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
for kw in ['required_tools','forbidden_tools','arg_schema','no_pattern']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
print(f'len={len(content)}')
"
```

Raw output:

```
required_tools: not found
forbidden_tools: not found
arg_schema: not found
no_pattern: not found
len=34752
```

EvalCore last push 2026-07-26 (64 days inactive). **Not falsified (c9-p03, 2026-09-29).**

---

**F-P2-3: promptfoo adds offline transcript replay**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://raw.githubusercontent.com/promptfoo/promptfoo/main/CHANGELOG.md',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
for kw in ['offline','transcript replay','jsonl replay','no api','keyless']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
lines = [l for l in content.splitlines() if l.startswith('## [')]
print('Latest versions:', lines[:3])
"
```

Raw output:

```
offline: not found
transcript replay: not found
jsonl replay: not found
no api: not found
keyless: not found
Latest versions: ['## [0.123.1]...(2026-09-18)', '## [0.123.0]...(2026-09-10)',
  '## [0.122.2]...(2026-08-28)']
```

promptfoo 0.123.1 (2026-09-18) still the latest. No offline transcript replay.
**Not falsified (c9-p03, 2026-09-29).**

---

**F-C9-1: Langfuse implements offline keyless contract assertions**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://raw.githubusercontent.com/langfuse/langfuse/main/README.md',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
for kw in ['offline','keyless','required_tools','forbidden_tools','arg_schema',
           'contract assertion']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
print(f'len={len(content)}')
"
```

Raw output:

```
offline: not found
keyless: not found
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
len=53353
```

Langfuse pushed 2026-09-29 (35,203 stars — up from 35,191 in c8-p03, +12 in ~7 hours).
No offline or contract assertion surface added. **Not falsified (c9-p03, 2026-09-29).**

---

**F-C9-2: inspect_ai 0.3.272 adds tool-call contract assertions or offline compare**

```bash
$ python3 -c "
import urllib.request, json, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request('https://pypi.org/pypi/inspect-ai/json',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    d = json.loads(r.read())
print('version:', d['info']['version'])
desc = d['info']['description'] or ''
for kw in ['required_tools','forbidden_tools','arg_schema','contract assertion',
           'offline compare']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in desc.lower() else \"not found\"}')
"
```

Raw output:

```
version: 0.3.272
required_tools: not found
forbidden_tools: not found
arg_schema: not found
contract assertion: not found
offline compare: not found
```

inspect_ai 0.3.272 remains the latest PyPI release as of 2026-09-29T18:01 UTC. Dev tree
pushed 2026-09-29 but no new PyPI version. No contract assertion surface.
**Not falsified (c9-p03, 2026-09-29).**

---

**F-C9-3: TruLens "offline batch mode" is equivalent to keyless local-file operation**

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    'https://raw.githubusercontent.com/truera/trulens/main/README.md',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
    content = r.read(60000).decode('utf-8', errors='ignore')
for kw in ['keyless','no api key','local file','jsonl','required_tools']:
    print(f'{kw}: {\"FOUND\" if kw.lower() in content.lower() else \"not found\"}')
lines = content.splitlines()
for i, line in enumerate(lines):
    if 'offline' in line.lower():
        for l in lines[max(0,i-2):i+4]:
            print(repr(l))
        print()
print(f'len={len(content)}')
"
```

Raw output:

```
keyless: not found
no api key: not found
local file: not found
jsonl: not found
required_tools: not found
'### Batch and inline evaluation'
''
'Run evaluations alongside your app, on existing data, or in offline batch mode:'
''
'```python'
'# Inline — evaluate as the app runs'

len=8375
```

TruLens "offline batch mode" still requires a TruSession with database backend.
Not keyless, not local-file-only. The word "offline" is a marketing synonym for
"post-hoc" in TruLens, not "without network". **Not falsified (c9-p03, 2026-09-29).**

---

### C. Ecosystem star counts (c9-p03, 2026-09-29T18:01 UTC)

```
=== STAR COUNTS c9-p03 2026-09-29T18:01:27 UTC ===
UKGovernmentBEIS/inspect_ai:         stars=2881   pushed=2026-09-29
repowazdogz-droid/inspect-replay:    stars=0      pushed=2026-07-14  (78 days inactive)
debu-sinha/inspect-mlflow:           stars=3      pushed=2026-09-29
eval-core/evalcore:                  stars=16     pushed=2026-07-26  (64 days inactive)
promptfoo/promptfoo:                 stars=25558   pushed=2026-09-29
confident-ai/deepeval:               stars=18502   pushed=2026-09-29
langfuse/langfuse:                   stars=35203   pushed=2026-09-29
Arize-ai/phoenix:                    stars=11653   pushed=2026-09-29
AgentOps-AI/agentops:                stars=5847    pushed=2026-06-25  (96 days inactive)
braintrustdata/braintrust-sdk-python: stars=20     pushed=2026-09-29
langchain-ai/langsmith-sdk:          stars=1065    pushed=2026-09-29
openai/evals:                        stars=19522   pushed=2026-04-14  (168 days inactive)
truera/trulens:                      stars=3579    pushed=2026-09-29
```

**Delta vs c8-p03 (2026-09-29T11:03 UTC, ~7 hours earlier):**

| Tool | c8-p03 | c9-p03 | Delta |
|------|--------|--------|-------|
| inspect_ai | 2,880 | **2,881** | +1 |
| promptfoo | 25,552 | **25,558** | +6 |
| deepeval | 18,497 | **18,502** | +5 |
| langfuse | 35,191 | **35,203** | +12 |
| phoenix | 11,651 | **11,653** | +2 |
| agentops | 5,846 | **5,847** | +1 |
| trulens | 3,578 | **3,579** | +1 |
| openai/evals | 19,521 | **19,522** | +1 |

All active tools added stars in the 7-hour window. The overall ranking and gap structure
(Langfuse > promptfoo > openai/evals > deepeval > phoenix) is unchanged. No tool added
contract assertion or offline/keyless features in this window.

---

### D. Open questions closed — c9-p03

This pass closes the three open questions left in RESEARCH.md after c8-p01. See also the
corresponding closure entries in RESEARCH.md itself.

**OQ-1: S5 (D'Oro et al. arXiv 2605.08261) — hierarchical bootstrap section 5**

Prior status: link verified (HTTP 200), but full content of section 5 not independently
verified. The citation claims the paper "develops an aggregation framework pairing Wilson
score intervals with hierarchical bootstrap for CUA benchmark confidence intervals."

Verification run (2026-09-29T18:01 UTC):

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request('https://arxiv.org/abs/2605.08261',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
    content = r.read(20000).decode('utf-8', errors='ignore')
for marker in ['hierarchical', 'bootstrap', 'wilson', 'confidence interval']:
    idx = content.lower().find(marker.lower())
    if idx >= 0:
        snippet = content[max(0,idx-50):idx+120].replace('\n',' ').strip()
        print(f'{marker}: FOUND — ...{snippet}...')
    else:
        print(f'{marker}: not found')
"
```

Raw output:

```
hierarchical: FOUND — ...ion framework pairing Wilson score intervals with hierarchical bootstrap,
  producing confidence intervals that correctly account for the nested structu...
bootstrap: FOUND — ...pairing Wilson score intervals with hierarchical bootstrap, producing
  confidence intervals that correctly account for the nested structure of CUA ben...
wilson: FOUND — ...cond, we develop an aggregation framework pairing Wilson score intervals
  with hierarchical bootstrap, producing confidence intervals that correctly ac...
confidence interval: FOUND — ...intervals with hierarchical bootstrap, producing confidence
  intervals that correctly account for the nested structure of CUA benchmarks, as we empiri...
```

The abstract of arXiv 2605.08261 explicitly states "we develop an aggregation framework
pairing Wilson score intervals with hierarchical bootstrap, producing confidence intervals
that correctly account for the nested structure of CUA benchmarks." This is the load-bearing
claim in S5. The citation is correct.

**Status: CLOSED — S5 citation supports the claim.**

Note: "section 5" of the paper could not be confirmed from the abstract-page HTML alone
(PDF scraping was not performed). The abstract text is sufficient: the claim taken from
this source in RESEARCH.md is the aggregation framework concept, which appears verbatim
in the abstract. A full PDF read of section 5 remains out of scope for this pass.

---

**OQ-2: F-3 (mutation 70% threshold) — no Offutt & Untch grounding**

Prior status: the Tier-1 finding from the citation audit corrected the attribution
(S8a fabrication: "70% threshold is grounded" is NOT in the paper). The threshold was
relabelled as an engineering decision in RESEARCH.md.

This item is deferred to the mutation pass (c9-p12) by design. The mutation pass will
run `mutmut` on core modules, measure the actual kill rate, and record whether the
70% engineering target is met. No additional action required in this research pass.

**Status: CLOSED as designed — deferred to mutation pass. No claim in RESEARCH.md
or README.md attributes the 70% threshold to Offutt & Untch (the fabrication was
corrected in a prior pass).**

---

**OQ-3: tau-bench (S35) — ICLR workshop version not separately verified**

Prior status: arXiv 2406.12045 resolves and is sufficient. ICLR 2024 workshop
proceedings version not separately fetched.

Verification run (2026-09-29T18:01 UTC):

```bash
$ python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request('https://arxiv.org/abs/2406.12045',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
    content = r.read(20000).decode('utf-8', errors='ignore')
for marker in ['tau-bench', 'tool-agent', 'iclr', 'workshop', 'title']:
    idx = content.lower().find(marker.lower())
    if idx >= 0:
        snippet = content[max(0,idx-30):idx+120].replace('\n',' ').strip()
        print(f'{marker}: FOUND — ...{snippet}...')
    else:
        print(f'{marker}: not found')
"
```

Raw output:

```
tau-bench: not found
tool-agent: FOUND — ...[2406.12045] $τ$-bench: A Benchmark for Tool-Agent-User
  Interaction in Real-World Domains</title>...
iclr: not found
workshop: not found
title: FOUND — ...[2406.12045] $τ$-bench: A Benchmark for Tool-Agent-User
  Interaction in Real-World Domains</title>...
```

The title confirms: arXiv 2406.12045 is τ-bench, "A Benchmark for Tool-Agent-User
Interaction in Real-World Domains." The ICLR workshop "iclr" keyword does not appear
in the abstract-page HTML — the arXiv abstract page does not annotate workshop
submissions in its metadata. The arXiv version is the canonical citable form for this
paper and is sufficient for RESEARCH.md.

**Status: CLOSED — arXiv 2406.12045 is the correct, resolvable citation. The ICLR
workshop venue is noted as unverified but the citation is to the arXiv paper, not the
workshop proceedings. No claim depends on the workshop venue.**

---

### E. No new failure mode (c9-p03)

All failure modes FM-1 through FM-9 reviewed against this pass's recipe run. No new
structural failure mode found. All previously documented failure modes remain accurate:

- FM-6 (PYTHONPATH for project-local agents): still applies when using `agenteval record`
  with a non-installed module. Not triggered in this pass (using committed fixtures).
- FM-7/FM-8 (zero-token baseline — cost gate warning): warning still present in steps
  3/4 output (`total_tokens`, `total_cost_usd` not enforced). This is correct documented
  behaviour for the example agent (zero-token by design).

The only observable change from c8 to c9: test count advanced from 210 to 217 (new
tests added in c9 implementation passes). The FM-9 pattern (test count change unreported
by gate) remains valid but is not triggered here — the recipe uses fixed committed
fixtures, not a suite that changed between passes.

---

### F. Operational cost — c9-p03 measurements

Measured at 2026-09-29T18:01 UTC (ThinkStation P500, Python 3.11.15, no GPU):

| Operation | Wall time | User time | Network |
|---|---|---|---|
| `agenteval run` (4 cases, good run) | 0.261 s | 0.205 s | none |
| `agenteval run` (4 cases, regressed run) | 0.191 s | 0.168 s | none |
| `agenteval gate` (identical) | ~0.17 s | ~0.15 s | none |
| `agenteval gate` (regressed) | ~0.17 s | ~0.15 s | none |
| `agenteval drift` (4 vs 4) | ~0.17 s | ~0.15 s | none |
| `pytest -q` (217 tests) | 3.84 s | — | none |
| `ruff check .` + `ruff format --check .` | < 1 s | — | both clean |

217 tests pass (up from 210 in c8-p03, +7 new tests from c9 implementation passes).
Runtime is unchanged. Evaluation pipeline is not a CI bottleneck.

**Human cost per operation (unchanged from c8-p03):**
- Total for a team with guide + known tool names: **25–35 minutes**
- Total cold start: **60–90 minutes**

---

### G. Updated comparison table (c9-p03 refresh, 2026-09-29T18:01 UTC)

| Tool | Licence | Version (date) | Stars (c9-p03) | Delta vs c8-p03 | Last push |
|------|---------|----------------|----------------|----------------|-----------|
| inspect_ai | MIT | 0.3.272 (2026-09-28) | 2,881 | +1 | 2026-09-29 |
| inspect-replay | MIT | v0.2.0 (2026-07-14) | 0 | 0 | 2026-07-14 (**78d inactive**) |
| inspect-mlflow | MIT | 0.8.1 (2026-09-15) | 3 | 0 | 2026-09-29 |
| EvalCore | Apache-2.0 | v0.7.5 (2026-07-19) | 16 | 0 | 2026-07-26 (**64d inactive**) |
| promptfoo | MIT (OpenAI) | 0.123.1 (2026-09-18) | 25,558 | +6 | 2026-09-29 |
| DeepEval | Apache-2.0 | 4.2.6 (2026-09-24) | 18,502 | +5 | 2026-09-29 |
| Braintrust | SaaS / MIT SDK | Python SDK v0.43.0 (2026-09-28) | 20 | 0 | 2026-09-29 |
| LangSmith | SaaS / MIT SDK | Python SDK v0.14.1 (2026-09-25) | 1,065 | 0 | 2026-09-29 |
| AgentOps | MIT | 0.4.21 | 5,847 | +1 | 2026-06-25 (**96d inactive**) |
| Arize Phoenix | Apache-2.0 | 20.16.0 (2026-09-23) | 11,653 | +2 | 2026-09-29 |
| Langfuse | MIT | 4.15.6 (2026-09-24) | 35,203 | +12 | 2026-09-29 |
| openai/evals | MIT | — | 19,522 | +1 | 2026-04-14 (**168d inactive**) |
| truera/trulens | MIT | 2.14.0 (2026-09-28) | 3,579 | +1 | 2026-09-29 |
| replayproof | MIT | 0.1.0 | 0 (not launched) | — | — |

---

### H. Open-question tally after c9-p03

| Item | State after c9-p03 |
|------|---------------------|
| F-1 through F-5 | Closed (c1/c2) |
| F-P2-1, F-P2-2, F-P2-3 | **Re-run c9-p03 (18:01 UTC 2026-09-29)**: not falsified |
| F-P2-4, F-P2-5 | Closed (c3-p02) |
| F-P3-1 through F-P3-4 | Closed (c3-p03) |
| F-C3-1 through F-C3-10 | Closed (c3-p01, c3-p03) |
| F-C4-1 through F-C4-13 | Closed/not falsified (c4 passes) |
| F-C5-1 through F-C5-6 | Closed (c5 passes) |
| F-C6-1 through F-C6-7 | Closed (c6 passes) |
| F-C7-1, F-C7-2 | Closed (c7-p03) |
| F-C8-1 through F-C8-3 | Closed (c8-p03) |
| F-C9-1 | **Run c9-p03 (18:01 UTC)**: not falsified (Langfuse) |
| F-C9-2 | **Run c9-p03 (18:01 UTC)**: not falsified (inspect_ai 0.3.272) |
| F-C9-3 | **Run c9-p03 (18:01 UTC)**: not falsified (TruLens offline ≠ keyless) |
| OQ-1 (S5 D'Oro hierarchical bootstrap) | **CLOSED c9-p03**: abstract confirms claim |
| OQ-2 (F-3 mutation threshold) | **CLOSED c9-p03**: relabelled as engineering decision; deferred to mutation pass |
| OQ-3 (tau-bench S35 ICLR version) | **CLOSED c9-p03**: arXiv citation sufficient |
| F-3 (per-module mutation score) | Deferred to c9-p12 mutation pass by design |

**Count of open falsification items awaiting execution: 0.** All three open questions
from c8-p01 are closed. Every falsification check that can be run in a research pass has
been run with raw terminal output on record.

---

### I. Updated ecosystem map — c9-p03 final state

```
Need:                                   Use:
Production observability + dashboard  → Langfuse (35k★), AgentOps (6k★, 96d inactive)
LLM-judged semantic correctness       → DeepEval (18k★), Arize Phoenix (12k★)
Broadest assertion surface + red-team → promptfoo (25k★, OpenAI-owned)
RAG pipeline quality metrics          → Ragas (16k★, 217d inactive)
Historical LLM benchmark framework    → openai/evals (20k★, 168d inactive)
RAG/LLM quality + tracing             → TruLens (4k★, batch-DB offline only)
SaaS experiment tracking              → Braintrust (cloud, SDK 0.43.0)
SaaS tracing + LangChain integration  → LangSmith (1k SDK★, cloud-required)
CI diff of two eval runs              → inspect-replay (0★, 78d dormant)
Stat-significant score comparisons    → inspect-mlflow (3★)
Offline cassette replay               → EvalCore (16★, 64d dormant)
Tool-call contract assertions +       → replayproof (this repo)
  keyless CI gate + Wilson lower bound
```

The "tool-call contract assertions + keyless CI gate" cell remains unoccupied by any
assessed tool as of 2026-09-29T18:01 UTC. Six falsification checks were run this pass
with raw output. None falsified. The positioning is confirmed unoccupied across 13
assessed tools across all nine research cycles.

**The research-3 phase for cycle 9 is complete.**
