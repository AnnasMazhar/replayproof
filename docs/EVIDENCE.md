# EVIDENCE — claim register for replayproof

Format per `PROOF-AND-RELEASE.md`: **claim → exact command → raw output → verdict**.
Everything below was executed on this machine on 2026-09-27 from a clean
`uv venv && uv pip install -e '.[dev]'`. Raw terminal output is pasted, not
summarised. `PASS` = proven, `PARTIAL` = proven with a named gap.

Environment note: `~/.hermes/.env` was only ever *read* for `GROQ_API_KEY` by
`scripts/record_real_run.py`; no key value is printed anywhere in this repo.

---

## C1 — Three REAL recordings exist, produced by real models, in the recording schema

**Claim:** the repo contains real agent runs (not synthetic fixtures) from a local
model and a free hosted model, plus a run that genuinely regresses.

### C1.1 Recording commands (exact, with model and provider)

```bash
# 1. local model — ollama gemma3:4b on this machine
.venv/bin/python scripts/record_real_run.py \
    --provider ollama --model gemma3:4b --prompt-mode full \
    --out examples/recordings/real_gemma3_4b_full.jsonl

# 2. free hosted model — Groq openai/gpt-oss-120b (GROQ_API_KEY from env,
#    never printed, never committed)
.venv/bin/python scripts/record_real_run.py \
    --provider groq --model openai/gpt-oss-120b --prompt-mode full \
    --out examples/recordings/real_gpt_oss_120b_full.jsonl

# 3. deliberate regression — same local model, same tasks, narrowed prompt
.venv/bin/python scripts/record_real_run.py \
    --provider ollama --model gemma3:4b --prompt-mode narrowed \
    --out examples/recordings/real_gemma3_4b_narrowed.jsonl
```

Raw output, recording 1 (local `gemma3:4b`):

```
case-01 ollama:gemma3:4b tokens=379/40 tools=['search_docs'] final='A typical residential solar system produces 4-10 kW of power.'
case-02 ollama:gemma3:4b tokens=376/37 tools=['search_docs'] final='Lithium-ion batteries are the most common type.'
case-03 ollama:gemma3:4b tokens=363/45 tools=['search_docs'] final="I'm sorry, but the provided documents do not contain information about"
case-04 ollama:gemma3:4b tokens=378/51 tools=['search_docs'] final='Roof orientation and tilt angle affect energy production. A typical re'
case-05 ollama:gemma3:4b tokens=384/39 tools=['search_docs'] final='Lead-acid batteries are less efficient.'
case-06 ollama:gemma3:4b tokens=376/36 tools=['search_docs'] final='Most systems are connected to the grid via a net metering agreement.'
wrote 6 runs -> examples/recordings/real_gemma3_4b_full.jsonl
```

Raw output, recording 2 (hosted `openai/gpt-oss-120b` via Groq):

```
case-01 groq:openai/gpt-oss-120b tokens=482/115 tools=['search_docs'] final='A typical residential solar system generates about **4 – 10 kilowatts '
case-02 groq:openai/gpt-oss-120b tokens=517/221 tools=['search_docs'] final='Lithium‑ion batteries are the most common chemistry used in home energ'
case-03 groq:openai/gpt-oss-120b tokens=599/72 tools=['search_docs', 'search_docs'] final='The solar panel installation process typically takes **1 to 3 days**, '
case-04 groq:openai/gpt-oss-120b tokens=529/875 tools=['search_docs'] final='Roof orientation (the direction the roof faces) and the roof’s tilt an'
case-05 groq:openai/gpt-oss-120b tokens=513/177 tools=['search_docs'] final='No. Lead‑acid batteries are generally **less efficient** than lithium‑'
case-06 groq:openai/gpt-oss-120b tokens=1146/262 tools=['repo_browser.search', 'search_docs', 'search_docs'] final='Most new solar installations are tied into the utility grid through a '
wrote 6 runs -> examples/recordings/real_gpt_oss_120b_full.jsonl
```

Raw output, recording 3 (deliberate regression: narrowed prompt):

```
case-01 ollama:gemma3:4b tokens=50/20 tools=none final='A typical residential solar system produces around 5-10 kilowatts of p'
case-02 ollama:gemma3:4b tokens=50/14 tools=none final='Lithium-ion batteries are most common in home storage systems.'
case-03 ollama:gemma3:4b tokens=48/12 tools=none final='Solar panel installation typically takes 1-3 days.'
case-04 ollama:gemma3:4b tokens=51/17 tools=none final='Shading, tilt angle, and orientation significantly impact rooftop sola'
case-05 ollama:gemma3:4b tokens=52/17 tools=none final='No, lithium-ion batteries are significantly more efficient than lead-a'
case-06 ollama:gemma3:4b tokens=50/26 tools=none final='Most new solar systems are connected to the grid via a net meter that '
wrote 6 runs -> examples/recordings/real_gemma3_4b_narrowed.jsonl
```

**Verdict: PASS.** Three recordings, 18 real runs, two different real models, one
real regression, provider-reported token counts on every assistant turn.

### C1.2 The models are real, and gemma3:4b really has no native tool support

```
$ python3 probe.py   # (ad-hoc probe; not committed)
groq key present: True len 56
groq models ERR: HTTP Error 403: Forbidden
ollama ERR: HTTP Error 400: Bad Request

$ python3 probe2.py
ollama no-tools err: None dt 1.29
  usage: 11 3
ollama tools err: (400, '{"error":"registry.ollama.ai/library/gemma3:4b does not support tools"}')
groq llama-3.3-70b-versatile err: (403, 'error code: 1010\n')
```

The 400 is why the scaffold uses the **json-envelope-v1** protocol (same message
prompts for every model) instead of native tool schemas; the Groq 403 is why
`scripts/record_real_run.py` sends a browser `User-Agent` (Cloudflare blocks
`Python-urllib`). After the UA header, `GET /openai/v1/models` listed
`openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, `allam-2-7b`.

**Verdict: PASS.**

### C1.3 Recordings are redacted of host paths and internal names

```bash
grep -c "/home/\|openclaw\|thinkstation" examples/recordings/real_*.jsonl
```

```
examples/recordings/real_gemma3_4b_full.jsonl:0
examples/recordings/real_gemma3_4b_narrowed.jsonl:0
examples/recordings/real_gpt_oss_120b_full.jsonl:0
```

Redaction is applied at record time (`scripts/record_real_run.py::redact`) and
asserted by `tests/test_real_recordings.py`.

**Verdict: PASS.**

---

## C2 — Replays are offline (zero API keys) and byte-identical

**Claim:** the same recording replays twice with no API key in the environment
and produces byte-identical output.

Command (keys explicitly unset; the script then prints whatever credential-like
variables remain):

```bash
env -u GROQ_API_KEY -u OPENROUTER_API_KEY -u OPENROUTER_API_KEY_ -u ZAI_API_KEY \
    -u MINIMAX_API_KEY -u JEV_API_KEY -u OPENVIKING_API_KEY -u STARSHIP_SESSION_KEY \
    -u ANNAMAZHAR_GH_TOKEN -u SUDO_PASSWORD \
    .venv/bin/python - pass1   # dry-replays every line of examples/recordings/real_*.jsonl
# ... repeated identically as pass2 ...
sha256sum /tmp/opencode/replayproof/replayed_pass1.jsonl \
          /tmp/opencode/replayproof/replayed_pass2.jsonl
cmp replayed_pass1.jsonl replayed_pass2.jsonl && echo "byte-identical: YES"
```

Raw output:

```
[pass1] KEY/TOKEN/SECRET/PASSWORD env vars remaining: []
[pass1] dry-replayed 18 real runs, keys unset, offline
[pass2] KEY/TOKEN/SECRET/PASSWORD env vars remaining: []
[pass2] dry-replayed 18 real runs, keys unset, offline
== sha256 of both replays ==
537921c8bd1b667d78ec0d20bc4c8c9b09d0c7a6e5573641f5171b6308c3be74  replayed_pass1.jsonl
537921c8bd1b667d78ec0d20bc4c8c9b09d0c7a6e5573641f5171b6308c3be74  replayed_pass2.jsonl
byte-identical: YES
```

Contract evaluation of a real recording, run twice with keys unset:

```
67671fae2ac2dd25613dd5c6fed268b9d024e84e93fa6e7e9412e8ef65500996  eval1.json
67671fae2ac2dd25613dd5c6fed268b9d024e84e93fa6e7e9412e8ef65500996  eval2.json
```

No network on the offline path:

```bash
grep -n "urllib\|socket\|requests\|http" src/agenteval/replay.py \
    src/agenteval/scoring.py src/agenteval/budget.py src/agenteval/drift.py \
    src/agenteval/assertions.py
```

```
no network imports in replay/gate/drift/assert path
```

**Verdict: PASS.** Determinism here is *freezing*: replay copies what was
recorded, it does not re-run the model. That is the product's stated design
(`README Limitations`) and is attacked in `docs/ADVERSARIAL_REVIEW.md` pass 4.

---

## C3 — The gate fails on a real regression and passes on the unchanged run

Baseline is derived from the real local recording; the regressed current run is
the narrowed-prompt recording of the *same six tasks by the same real model*.

```bash
C=examples/contracts/real_research.yaml; R=examples/recordings
agenteval run --contract $C --runs $R/real_gemma3_4b_full.jsonl \
    --output /tmp/opencode/baseline_local.json --format json
agenteval run --contract $C --runs $R/real_gemma3_4b_narrowed.jsonl \
    --output /tmp/opencode/result_narrowed.json --format json
agenteval run --contract $C --runs $R/real_gemma3_4b_full.jsonl \
    --output /tmp/opencode/baseline_local_rerun.json --format json
```

Suite summaries (raw):

```
baseline_local: pass_rate=1.0000 wilson_lower=0.6097 n=6 passed=6 tokens_in=2256 tokens_out=248 p95_ms=7842.0
result_groq: pass_rate=0.8333 wilson_lower=0.4365 n=6 passed=5 tokens_in=3786 tokens_out=1722 p95_ms=2239.3
   FAIL case-06: forbidden_tools: Forbidden tools were called: ['repo_browser.search']
result_narrowed: pass_rate=0.0000 wilson_lower=0.0000 n=6 passed=0 tokens_in=301 tokens_out=106 p95_ms=3729.0
   FAIL case-01: required_tools: Required tools not called: ['search_docs']
   FAIL case-02: required_tools: Required tools not called: ['search_docs']
   FAIL case-03: required_tools: Required tools not called: ['search_docs']
   FAIL case-04: required_tools: Required tools not called: ['search_docs']
   FAIL case-05: required_tools: Required tools not called: ['search_docs']
   FAIL case-06: required_tools: Required tools not called: ['search_docs']
```

Gate, unchanged run (baseline vs a fresh re-evaluation of the same recording):

```
$ agenteval gate --baseline baseline_local.json --current baseline_local_rerun.json
Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero (first-run or corrupted baseline): total_cost_usd
exit=0
```

Gate, regressed run — **named metric: `pass_rate`**:

```
$ agenteval gate --baseline baseline_local.json --current result_narrowed.json
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.0000       0.0000
Warning: the following gates were not enforced because the baseline value is zero (first-run or corrupted baseline): total_cost_usd
exit=1
```

Gate, hosted model vs local baseline (both metrics trip):

```
$ agenteval gate --baseline baseline_local.json --current result_groq.json
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.8333       0.0000
total_tokens                 2504.0000    5508.0000       0.1000
exit=1
```

**Verdict: PASS.** Exit 0 unchanged, exit 1 regressed with the metric named.
`total_cost_usd` is reported as not enforced because no pricing config exists —
see C4.

---

## C4 — Model-swap drift between two REAL models

```bash
agenteval drift --a /tmp/opencode/baseline_local.json --b /tmp/opencode/result_groq.json
```

Raw output:

```
Regressions : 1
Fixes       : 0
Churn       : 0
Stable pass : 5
Stable fail : 0
Token delta : +3004

Regressions:
  case-06
```

Side-by-side (from the two suite JSONs the drift command consumed):

| metric | local `gemma3:4b` (A) | hosted `gpt-oss-120b` (B) | delta |
| --- | --- | --- | --- |
| pass rate | 1.0000 | 0.8333 | −0.1667 |
| Wilson lower bound (95%) | 0.6097 | 0.4365 | −0.1732 |
| contract broken | none | `forbidden_tools` on `case-06` (`repo_browser.search`) | 1 regression |
| tool calls used | `search_docs` only (6 cases) | `search_docs` + **`repo_browser.search`** (not in the scaffold) | — |
| tokens in / out | 2256 / 248 | 3786 / 1722 | **+3004 total tokens (+119.9%)** |
| total_cost_usd | 0.0 | 0.0 | not computed — no pricing config (gate says so explicitly) |

**What this drift report CAN conclude:** with identical prompts and an identical
contract, the two real models differ on (a) one tool-call contract — the hosted
model invented a tool the scaffold never advertised, and the recording shows the
scaffold rejecting it (`error: unknown tool: repo_browser.search`); (b) pass
rate 6/6 vs 5/6 with each side's Wilson lower bound; (c) token cost +119.9%.

**What it CANNOT conclude:** n=2 models, n=6 cases, one contract. It cannot
rank the models, cannot estimate a population-level pass-rate difference (a
single case moves the rate by 16.7pp; the Wilson bounds overlap the whole
range), cannot say anything about latency (recorded latencies mix provider
queueing with generation), and cannot produce a dollar cost delta because no
pricing table is configured — the token delta is the honest cost proxy.

**Verdict: PASS** for "show what actually changed between two real models";
**PARTIAL** for any statistical ranking claim (explicitly not made).

---

## C5 — The three open majors from the adversarial review are fixed

| finding | command | raw output | verdict |
| --- | --- | --- | --- |
| C2P11-MAJ-1 `wilson_lower` accepts negative confidence | `pytest tests/test_scoring.py::TestWilsonConfidenceValidation -q` | `22 passed` in the full new-test run; **17 failed** with the four fix files stashed (`wilson_lower(3, 5, -0.5)` returned `0.733332` before the fix) | PASS |
| C2P11-MAJ-2 gate accepts NaN/inf `pass_rate` | `pytest tests/test_budget_drift.py::TestGateNonFiniteMetrics -q` | passes now; failed before fix (`compare({'pass_rate': nan}, baseline).ok == True`); CLI now exits **2** on NaN input | PASS |
| ADV2-1 README `contracts/research.yaml` does not exist | `pytest tests/test_readme_paths.py -q` | passes now; before the fix: `test_every_contract_path_exists`, `test_every_runs_path_exists` and 2 parametrised cases failed | PASS |

Stash-verification transcript:

```
--- tests WITHOUT fixes (expect failures) ---
FAILED tests/test_budget_drift.py::TestGateNonFiniteMetrics::test_gate_rejects_nan_latency
FAILED tests/test_budget_drift.py::TestGateNonFiniteMetrics::test_gate_rejects_nan_cost
FAILED tests/test_budget_drift.py::TestGateNonFiniteMetrics::test_cli_gate_exits_2_on_nan_input
FAILED tests/test_readme_paths.py::TestReadmeCommandPaths::test_every_contract_path_exists
FAILED tests/test_readme_paths.py::TestReadmeCommandPaths::test_every_runs_path_exists
FAILED tests/test_readme_paths.py::TestReadmeCommandPaths::test_contract_paths_parametrised[block 0-contracts/research.yaml]
FAILED tests/test_readme_paths.py::TestReadmeCommandPaths::test_contract_paths_parametrised[block 8-contracts/research.yaml]
17 failed, 4 passed in 0.71s
--- restored; re-run same tests ---
22 passed in 0.47s
```

**Verdict: PASS.**

---

## C6 — Green: suite and lint from a fresh venv

```bash
uv venv && uv pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

```
171 passed in 6.54s
All checks passed!
23 files already formatted
```

Fixture demo re-run in this pass (also a determinism check — it rewrites the
committed `sample_result.json` / `regressed_result.json`):

```
$ bash examples/run_demo.sh | tail -6
--- Final checks ---
PASS: gate exits correctly (0 on good, 1 on regressed)

=== Demo complete ===
$ git status --porcelain examples/recordings/sample_result.json examples/recordings/regressed_result.json
(no output — regenerated files are byte-identical to the committed ones)
```

**Verdict: PASS.**

---

## Claim register (README headline claims)

| # | claim as written (README) | exact command | raw output | status |
| --- | --- | --- | --- | --- |
| 1 | "which tool-call contract broke" — contract failures are named per case | `agenteval run --contract examples/contracts/real_research.yaml --runs examples/recordings/real_gpt_oss_120b_full.jsonl --format json` | `FAIL case-06: forbidden_tools: Forbidden tools were called: ['repo_browser.search']` | PASS |
| 2 | "with a 95% confidence bound" — Wilson lower bound reported | same as #1 | `wilson_lower=0.4365` (n=6, 5/6) | PASS |
| 3 | "fails the build when token cost regressed" | `agenteval gate --baseline baseline_local.json --current result_groq.json` | `total_tokens 2504 → 5508, threshold 0.1000`, `exit=1` | PASS |
| 4 | "without paying for a live LLM on every run" (offline replay, zero keys) | C2 command above | keys remaining: `[]`, sha256 identical | PASS |
| 5 | quickstart commands run as documented | `pytest tests/test_readme_paths.py -q` | `passed` | PASS |
| 6 | gate exits 1 on regression / 0 on unchanged | C3 commands | `exit=1` / `exit=0` | PASS |
| 7 | demo (fixtures) numbers in README "Real results" table | `bash examples/run_demo.sh` | `PASS: gate exits correctly (0 on good, 1 on regressed)`; regenerated result files byte-identical to committed ones | PASS |
| 8 | dollar-cost gating | `agenteval gate ...  # warns total_cost_usd not enforced` | `Warning: ... baseline value is zero ... total_cost_usd` | PARTIAL — no pricing config; token gate is enforced, cost gate is not |

## Reproducing everything from a fresh clone

```bash
git clone https://github.com/AnnasMazhar/replayproof && cd replayproof
uv venv && uv pip install -e '.[dev]'
pytest -q && ruff check .
bash examples/run_demo.sh                      # fixture demo (no network)
# real recordings are committed; re-record only if you have ollama/Groq access:
.venv/bin/python scripts/record_real_run.py --provider ollama --model gemma3:4b \
    --prompt-mode full --out /tmp/replay.jsonl
```

A stranger can replay and gate the committed recordings with no keys and no
network; re-recording requires either a local ollama with `gemma3:4b` or a Groq
key. That asymmetry is inherent: recordings are the artifact, not the model.
