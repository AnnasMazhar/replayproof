# replayproof

[![CI](https://github.com/AnnasMazhar/replayproof/actions/workflows/ci.yml/badge.svg)](https://github.com/AnnasMazhar/replayproof/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Your eval framework tells you the score moved.
This tells you **which tool-call contract broke**, with a 95% confidence bound,
and **fails the build** when token cost regressed against your stored baseline.

For AI engineers who already record agent runs and want deterministic CI gates
without paying for a live LLM on every run.

```bash
git clone https://github.com/AnnasMazhar/replayproof && cd replayproof
python3 -m venv .venv && . .venv/bin/activate && pip install .
agenteval run --contract examples/contracts/research.yaml --runs examples/recordings/sample_run.jsonl --output /tmp/good.json
agenteval run --contract examples/contracts/research.yaml --runs examples/recordings/regressed_run.jsonl --output /tmp/bad.json
agenteval gate --baseline /tmp/good.json --current /tmp/bad.json   # exit 1 — the seeded regression trips the gate
```

Note: `pip install agent-eval-harness` installs a **different, unrelated package** on PyPI
(Franck Ndzomga, 2026-02-09). Install from the git URL above or from source — the PyPI name
`replayproof` is reserved for the v0.2 release.

## What problem this solves

Agent behaviour is software behaviour: it should be recorded, replayed, asserted, and
compared across model versions without requiring live API calls. Most LLM evaluation
frameworks require network access on every CI run, produce non-deterministic results, and
give no way to tell whether a model update regressed behaviour or just changed it. This
harness reads recorded runs — from your existing eval tool, or its own JSONL — and gates
CI on three questions: which tool-call contract broke, what the pass rate actually is
(not just the percentage, but a 95% Wilson lower bound), and whether token cost or latency
regressed against the baseline you committed.

Composable with Inspect AI, EvalCore, and any tool that writes JSONL or OpenAI-style
message lists. Not a runner — no models, no providers, no keys.

## Design

```
Record agent run  ──►  Run.jsonl  ──►  Contract.evaluate  ──►  CaseResult[]
                                              │
                               ┌──────────────┴──────────────┐
                               ▼                             ▼
                          SuiteResult                   SuiteResult
                         (current)                      (baseline)
                               │                             │
                               └──────────┬──────────────────┘
                                          ▼
                                     GateReport          DriftReport
                                   (CI pass/fail)     (model A vs B diff)
                                          │
                                          ▼
                                    Markdown / HTML report
```

## Install

```bash
pip install git+https://github.com/AnnasMazhar/replayproof
```

Or from source (no API keys needed — runs entirely offline):

```bash
git clone https://github.com/AnnasMazhar/replayproof
cd replayproof
uv venv && uv pip install -e '.[dev]'
```

## 60-second quickstart

```bash
# Run the end-to-end demo — uses committed fixture recordings, no LLM needed
bash examples/run_demo.sh
```

Or step by step:

```bash
# Evaluate the good sample run against the research contract
agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/sample_run.jsonl \
    --output /tmp/sample_result.json

# Evaluate the regressed run
agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/regressed_run.jsonl \
    --output /tmp/regressed_result.json

# Gate: verify regressed run fails
agenteval gate \
    --baseline /tmp/sample_result.json \
    --current /tmp/regressed_result.json
# Exit code 1 — regression detected
```

If this is useful, star the repo — it is how others find it.

## Real results

Generated from `bash examples/run_demo.sh` on 2026-09-27:

**Good run (sample_run.jsonl):**

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 4 |
| Pass Rate | 100.0% |
| Wilson Lower Bound (95%) | 51.0% |
| p95 Latency | 0.1 ms |

**Regressed run (regressed_run.jsonl):**

| Metric | Value |
| ------ | ----- |
| Cases | 4 |
| Passed | 2 |
| Pass Rate | 50.0% |
| Wilson Lower Bound (95%) | 15.0% |

**Drift:**

| Metric | Value |
| ------ | ----- |
| Regressions | 2 |
| Fixes | 0 |
| Stable pass | 2 |

Gate exit code: 1 on regressed run, 0 on good run.

Token counts show as 0 because the demo agent (`research_agent.py`) is a deterministic
Python function — it has no LLM and therefore no token accounting. Token regression
gating is active for runs that do include token counts (real LLM recordings).

## How the gates work

The gate compares four metrics between a stored baseline and the current run:

- **pass_rate**: any drop triggers (threshold 0.0 by default, configurable)
- **total_tokens**: increase > 10% triggers
- **p95_latency_ms**: increase > 25% triggers
- **total_cost_usd**: increase > 10% triggers

Pass rates are reported with a **Wilson score interval lower bound** at 95% confidence.
This is more conservative than the normal approximation near p=0 and p=1, which is
where real eval suites operate (pass rates cluster near 100% or drop sharply on regression).

For a suite with 4/4 passing, the Wilson lower bound is 51.0% — reflecting that a sample
of 4 is too small to claim high reliability, even with 100% observed pass rate. This
prevents false confidence from small suites.

Reference: Wilson (1927), *JASA* 22(158):209-212. Applied to LLM evals:
D'Oro et al. (2026), arxiv 2605.08261.

## Contract YAML

Declare what a correct agent run looks like:

```yaml
# contracts/research.yaml
name: research
checks:
  - type: required_tools
    id: required_tools
    severity: error
    names: [search_docs]
  - type: forbidden_tools
    id: forbidden_tools
    severity: error
    names: [send_email]
  - type: max_tool_calls
    id: max_tool_calls
    severity: error
    n: 6
  - type: max_tokens
    id: max_tokens
    severity: warn
    n: 4000
  - type: no_pattern
    id: no_pii_email
    severity: error
    field_name: final_content
    regex: '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
```

## Integration with Inspect AI

If your team already runs `inspect_ai` evals, use the included bridge script to convert
their `.eval` archives. It handles both the current multi-file layout (`header.json` +
`samples/<id>.json`) and the legacy single-file layout (`log.json`):

```python
# scripts/convert_inspect_log.py — convert an Inspect AI .eval log to replayproof JSONL
import json, zipfile
from pathlib import Path
from agenteval.record import from_messages
from agenteval.transcript import Run

def _load(eval_path):
    with zipfile.ZipFile(eval_path) as z:
        names = z.namelist()
        if "log.json" in names:
            with z.open("log.json") as f:
                log = json.load(f)
            return log, log.get("samples", [])
        header = json.loads(z.read("header.json")) if "header.json" in names else {}
        samples = [json.loads(z.read(n)) for n in sorted(names) if n.startswith("samples/")]
        return header, samples

def convert(eval_path, out_dir):
    out = Path(out_dir); out.mkdir(exist_ok=True)
    header, samples = _load(eval_path)
    runs = []
    for sample in samples:
        messages = []
        for event in sample.get("events", []):
            if event.get("event") != "model": continue
            usage = event.get("output", {}).get("usage") or {}
            for msg in event.get("output", {}).get("choices", [{}]):
                content = dict(msg.get("message", {}))
                if usage and "tokens_in" not in content:
                    content["tokens_in"] = usage.get("input_tokens", 0)
                    content["tokens_out"] = usage.get("output_tokens", 0)
                messages.append(content)
        if messages:
            runs.append(from_messages(messages, name=str(sample.get("id", "unknown")),
                agent_id="inspect-agent",
                model=header.get("eval", {}).get("model", "unknown"), provider="inspect"))
    out_file = (out / Path(eval_path).stem).with_suffix(".jsonl")
    with open(out_file, "w") as f:
        for run in runs: f.write(run.to_jsonl() + "\n")
    print(f"Wrote {len(runs)} runs to {out_file}")
```

```bash
python scripts/convert_inspect_log.py logs/my_eval.eval recordings/
agenteval run --contract contracts/research.yaml --runs recordings/my_eval.jsonl --output baseline.json
agenteval gate --baseline baseline.json --current recordings/my_eval_new.jsonl
```

See [docs/ADOPTION.md](docs/ADOPTION.md) for a full step-by-step integration guide, including
CI YAML and a concrete failure mode walkthrough.

## Recording your own agent

```bash
# Agent module must expose a build_tools() factory if it needs tools.
# The --agent flag takes a dotted module path and callable name.
agenteval record \
    --agent examples.research_agent:research_agent \
    --task "How do solar panels work" \
    --output recordings/new_run.jsonl
```

Then use `agenteval run` to evaluate it against a contract, as shown above.

Each check has a stable `id`, `severity` (`error` or `warn`), and a named fault it
catches. See [docs/DESIGN.md](docs/DESIGN.md) for the full check reference.

## Where this fits relative to other tools

See [COMPARISONS.md](COMPARISONS.md) for a full factual table. The short version:

- **EvalCore** owns offline replay with a content-addressed cache — use it to record runs.
  This tool reads those recordings and asserts contracts over them.
- **inspect_ai + inspect-replay** owns sample-aligned log diffing — use it when the
  question is "which sample moved". Use this when the question is "which contract broke".
- **promptfoo** has the broadest tool-call assertion surface and 25k stars. Choose it for
  breadth and red-teaming. Choose this for deterministic, keyless, baseline-gated CI.

## Limitations

- **Replay cannot validate non-deterministic sampling.** Dry-mode replay freezes the LLM
  output; it does not test whether the LLM would produce the same output given live
  inputs. This is by design — the harness tests the deterministic scaffold (tool routing,
  argument handling, contract evaluation).

- **Judge-based scoring is not implemented.** There is no LLM-as-judge eval in v0.1.
  The `final_answer_matches` check uses regex; semantic correctness requires a separate
  judge layer.

- **Gate integrity relies on the caller.** `agenteval gate` reads a JSON file; it cannot
  verify the file was produced by an actual test run. In CI, the workflow must generate
  the file and pass it to the gate in the same job.

- **Wilson lower bound is conservative for small n.** For n < 10, the 95% Wilson lower
  bound may be too conservative to be useful as an absolute threshold. Use relative
  (drop-based) gates for small suites.

- **PII detection is regex-based.** The `no_pattern` check uses deterministic regexes.
  It detects structured PII (email, SSN, phone, credit card) but not free-form PII
  (names, addresses, unformatted numbers).

- **v0.1 does not read Inspect `.eval` logs.** It reads its own JSONL and normalises
  OpenAI/Anthropic-style message lists. Inspect log import is planned.

## Roadmap

- Inspect `.eval` log reader
- Hierarchical bootstrap for nested evaluation structures
- Judge-based scoring plugin API
- HTML report with per-case expandable details
- Cost estimation from provider pricing APIs
- Baseline integrity signing (HMAC or content-addressable storage)
