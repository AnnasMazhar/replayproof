# Improvement Log — agent-eval-harness

## c5-p09-improve-2: Fix fabricated EvalCore integration, README ecosystem omissions, gate JSONL error message (2026-09-28)

### Finding source

Systematic credibility audit of README.md against COMPARISONS.md (the repo's own research
document) and the CLI implementation. Three gaps found:

1. **BIGGEST GAP — fabricated EvalCore command sequence:** README showed:
   ```
   evalcore run --suite suite.yaml --cache replay --format jsonl --output /tmp/traces.jsonl
   agenteval run --runs /tmp/traces.jsonl ...
   ```
   COMPARISONS.md (c5-p02) explicitly states EvalCore reads "OTel / OpenInference exports
   and its own trajectory JSON. Not Inspect .eval, not message JSONL." The command implies
   EvalCore outputs message JSONL that `agenteval run` can consume natively — it does not.
   A skeptical reviewer running this snippet would get an error or wrong results. The README
   contradicted the repo's own research document.

2. **Selective comparison in "Where this fits":** Only 3 tools were named (EvalCore,
   inspect_ai+inspect-replay, promptfoo). Langfuse (35,141 stars — the largest tool in the
   space, added in c5-p02 COMPARISONS.md), AgentOps (5,847 stars), and Arize Phoenix
   (11,644 stars) were absent. Omitting the largest tool in the ecosystem looks cherry-picked.

3. **Unhelpful gate error when `--current` is a JSONL file:** Passing a `.jsonl` recording
   to `agenteval gate --current` gave: "not valid JSON: Extra data" — no recovery hint.
   A user who reads the EvalCore section and tries to pipe recordings directly to gate hits
   this wall with no idea what to do next.

### Root causes

**Gap 1:** The c5-p09 improve pass added the EvalCore integration section but used a command
from an earlier draft that assumed EvalCore outputs message JSONL. COMPARISONS.md was updated
in c4-p02/c5-p02 to reflect EvalCore's actual format, but the README was not updated to match.

**Gap 2:** The "Where this fits" section was written in c1-p09 before Langfuse/AgentOps/
Phoenix were added to COMPARISONS.md in c4-p02 and c5-p02. The section was never revisited
to include the newly-assessed tools.

**Gap 3:** The `_cmd_gate` JSON decode error handler was a generic fallback that printed the
raw exception message without checking whether the user had passed the wrong file type.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 187 passed |
| README EvalCore integration command | `evalcore run --format jsonl --output /tmp/traces.jsonl` (unsupported) |
| README "Where this fits" named tools | 3 (EvalCore, inspect_ai, promptfoo) |
| Langfuse (35k stars) mentioned in "Where this fits" | NO |
| `agenteval gate --current recording.jsonl` error | `"not valid JSON: Extra data"` (no recovery hint) |
| Test for actionable JSONL gate error | NONE |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 188 passed (+1) |
| README EvalCore integration | Honest prose: EvalCore outputs its own format; shows separate agenteval run step against agent's own JSONL |
| README "Where this fits" named tools | 6 (EvalCore, inspect_ai, promptfoo, Langfuse, AgentOps, Arize Phoenix) |
| Langfuse (35k stars) mentioned in "Where this fits" | YES — with star count |
| `agenteval gate --current recording.jsonl` error | "not a valid JSON suite result. … run it through the contract first: agenteval run --contract ... --runs ... --output result.json. Then pass result.json to agenteval gate --current result.json." |
| Test for actionable JSONL gate error | YES — `TestGateCLIActionableJSONLError.test_gate_cli_jsonl_current_error_is_actionable` |

### Evidence

Full test run:

```
$ cd /home/openclaw/portfolio/agent-eval-harness && .venv/bin/python -m pytest -q
........................................................................ [ 38%]
........................................................................ [ 76%]
............................................                             [100%]
188 passed in 2.75s
```

Ruff clean:

```
$ .venv/bin/ruff check . && .venv/bin/ruff format --check . && echo "RUFF CLEAN"
All checks passed!
21 files already formatted
RUFF CLEAN
```

New error message (before: "not valid JSON: Extra data"; after: actionable with recovery):

```
$ .venv/bin/agenteval gate --baseline /tmp/sample_result.json --current examples/recordings/sample_run.jsonl 2>&1; echo "Exit: $?"
error: 'examples/recordings/sample_run.jsonl' is not a valid JSON suite result.
The --current argument must be a JSON file produced by 'agenteval run --output'.
If you passed a JSONL recording, run it through the contract first:
  agenteval run --contract <contract.yaml> --runs <recording.jsonl> --output <result.json>
Then pass the result.json to 'agenteval gate --current result.json'.
Exit: 1
```

Demo still passes:

```
$ bash examples/run_demo.sh | grep -E "PASS: gate exits|Demo complete"
PASS: gate exits correctly (0 on good, 1 on regressed)
=== Demo complete ===
```

New test:

```
$ .venv/bin/python -m pytest tests/test_budget_drift.py::TestGateCLIActionableJSONLError -v
tests/test_budget_drift.py::TestGateCLIActionableJSONLError::test_gate_cli_jsonl_current_error_is_actionable PASSED
1 passed in 0.19s
```

### Files changed

- `README.md` — (1) `## Integration with EvalCore`: replaced the unsupported
  `evalcore run --format jsonl` pipe with honest prose explaining EvalCore uses its own
  OTel/trajectory format; corrected workflow to show agenteval run reading the agent's
  own JSONL separately from EvalCore's replay run. (2) `## Where this fits`: added
  Langfuse (35k stars), AgentOps (6k), Arize Phoenix (12k) as a fourth bullet covering
  the dominant observability/LLM-judge platforms.
- `src/agenteval/cli.py` — `_cmd_gate`: in the `json.JSONDecodeError` handler, detect
  whether the error is likely from a JSONL file (`.jsonl` extension or "extra data" in
  the exception message); if so, print an actionable 4-line error with the `agenteval run`
  recovery path instead of the raw exception text.
- `tests/test_budget_drift.py` — updated module docstring; added
  `TestGateCLIActionableJSONLError` class (1 test):
  `test_gate_cli_jsonl_current_error_is_actionable` — passes a `.jsonl` file as
  `--current`, asserts rc=1 and that stderr contains 'agenteval run'.
- `mutants/tests/test_budget_drift.py` — synced with tests/test_budget_drift.py
- `reports/improvements.md` — this entry

---



## c5-p08: Fix fabricated mutation score in EVIDENCE.md — write real mutation-c5.json (2026-09-28)

### Finding source

Quality-contract audit: EVIDENCE.md section 9 claimed data from `reports/mutation-c4.json`
that the file does not contain.

Exact discrepancy:
- EVIDENCE.md claimed: "Total mutants: 235, Killed: 223, Kill rate: 94.9%"
- reports/mutation-c4.json actually contains: `"rc": 1, "killed": null, "total": null, "kill_rate": null`

This is a fabricated evidence claim that violates QUALITY-CONTRACT §10 ("EVIDENCE.md is raw
terminal output, pasted verbatim … If you did not run it, it does not go in the file.").

### Root cause

In c5-p04, the `mutation-c4.json` file was committed with `rc=1` and null values because the
mutation runner had failed (the README path issue where the `test_readme_git_url_install_has_availability_note`
test couldn't find README.md at `mutants/README.md`). That failure was fixed via `conftest.py`
in the same c5-p04 commit, but the JSON committed at that time captured the failed run.

In c5-p05, the EVIDENCE.md refresh wrote "Kill rate: 94.9%" from the c4-p04 pass (which did
produce a real score of 94.8%) without reading the committed JSON file. The result: the section
pointed at mutation-c4.json as its source but the values in the markdown did not match the JSON.

No test existed that would fail when a mutation JSON has `rc=1` and null values — the only check
was whether the file existed.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 186 passed |
| EVIDENCE.md section 9 "Kill rate" claim | 94.9% (fabricated — not in mutation-c4.json) |
| EVIDENCE.md section 9 "Killed" claim | 223 (fabricated — mutation-c4.json has null) |
| reports/mutation-c4.json `rc` | 1 (runner failure) |
| reports/mutation-c4.json `killed` | null |
| reports/mutation-c5.json | MISSING |
| Test validating mutation JSON has real data | NONE |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 187 passed (+1) |
| EVIDENCE.md section 9 "Kill rate" claim | 94.8% — from reports/mutation-c5.json (real run) |
| EVIDENCE.md section 9 "Killed" claim | 221 — from reports/mutation-c5.json (real run) |
| reports/mutation-c5.json `rc` | 0 (success) |
| reports/mutation-c5.json `killed` | 221 |
| reports/mutation-c5.json `total` | 233 |
| reports/mutation-c5.json `kill_rate` | 0.9485 (94.8%) |
| Test validating mutation JSON has real data | YES — `TestMutationReportIntegrity.test_mutation_report_has_real_data` |

### Evidence

Mutation run (just completed, output from real mutmut run):

```
$ cd /home/openclaw/portfolio/agent-eval-harness && .venv/bin/mutmut run
    done in 664ms
Found 21 new tests, rerunning stats collection
    done
Running mutation testing
⠦ 233/233  🎉 221 🫥 0  ⏰ 0  🤔 0  🙁 12  🔇 0
15.87 mutations/second

$ .venv/bin/mutmut results
    agenteval.scoring.x_wilson_lower__mutmut_10: survived
    agenteval.scoring.x_wilson_lower__mutmut_11: survived
    agenteval.scoring.x_wilson_lower__mutmut_12: survived
    agenteval.scoring.x_wilson_lower__mutmut_69: survived
    agenteval.scoring.x__normal_quantile__mutmut_1: survived
    agenteval.scoring.x__normal_quantile__mutmut_3: survived
    agenteval.scoring.x__normal_quantile__mutmut_4: survived
    agenteval.scoring.x__normal_quantile__mutmut_5: survived
    agenteval.scoring.x__normal_quantile__mutmut_6: survived
    agenteval.scoring.x__normal_quantile__mutmut_19: survived
    agenteval.scoring.x__normal_quantile__mutmut_24: survived
    agenteval.scoring.x_compute_suite__mutmut_1: survived
```

Fault injection proof (test catches null values in mutation JSON):

```
$ python3 -c "
data = {'cycle': 5, 'rc': 1, 'killed': None, 'total': None, 'kill_rate': None}
assert data.get('rc') == 0, f'rc={data.get(\"rc\")} (expected 0)'
"
Traceback ... AssertionError: rc=1 (expected 0)
# Simulation confirms test WOULD fail for mutation-c4.json's contents.
```

Full test run:

```
$ .venv/bin/python -m pytest -q
........................................................................ [ 38%]
........................................................................ [ 77%]
...........................................                              [100%]
187 passed in 2.75s
```

New test:

```
$ .venv/bin/python -m pytest tests/test_report.py::TestMutationReportIntegrity -v
tests/test_report.py::TestMutationReportIntegrity::test_mutation_report_has_real_data PASSED
1 passed in 0.21s
```

Ruff clean:

```
$ .venv/bin/ruff check . && .venv/bin/ruff format --check . && echo "RUFF CLEAN"
All checks passed!
21 files already formatted
RUFF CLEAN
```

### Files changed

- `reports/mutation-c5.json` — NEW: real mutation run output (221/233 = 94.8%, rc=0,
  surviving mutants listed)
- `EVIDENCE.md` — section 9 rewritten: "Mutation score (cycle 5)" with real terminal
  output from the just-completed run; corrected kill count (221 not 223), total (233),
  rate (94.8% not 94.9%); note explaining why mutation-c4.json has null values
- `tests/test_report.py` — module docstring updated; added `TestMutationReportIntegrity`
  class (1 test): `test_mutation_report_has_real_data` — asserts reports/mutation-c5.json
  exists, has rc=0, integer killed/total, float kill_rate >0.70, and kill_rate is consistent
  with killed/total within 1%
- `mutants/tests/test_report.py` — synced with tests/test_report.py (identical)
- `reports/improvements.md` — this entry

---



### Finding source

Systematic audit of all CLI commands against the "actionable for strangers" bar.
Three commands (`replay`, `drift`, `report`) still emitted raw Python tracebacks on
missing-file input — the most common mistake a first-time user makes. The `run` and
`gate` commands were fixed in c1-p09 but the remaining three were missed.

Secondary fixes: README "Real results" date was `2026-09-27` (stale by one day after
the c4-p03 recipe was executed on 2026-09-28); EvalCore was named in "Where this fits"
with no code snippet — a skeptical reviewer has no way to verify the composability claim
without running the commands themselves.

### Root causes

**Raw tracebacks in drift/replay/report:** The c1-p09 improve pass wired actionable
error handling into `run` and `gate` but did not audit the remaining three subcommands
(`replay`, `drift`, `report`). Each of the three opened files with a bare `open()` call
and no `try/except FileNotFoundError` guard.

**README date stale:** The "Real results" section date was copied from c4-p08 and not
updated when c4-p03 ran the demo on 2026-09-28.

**EvalCore no code example:** MARKET-VERDICTS and COMPARISONS.md both name EvalCore as
the composable partner ("not a runner — reads recordings other tools make"), but the
README "Where this fits" section only gestured at EvalCore in prose. No command snippet
existed. ADOPTION.md has the full recipe (with EvalCore in the c2 deepening section)
but the README is the first surface a reviewer reads.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 176 passed |
| `agenteval drift --a missing.json ...` error | raw `FileNotFoundError` Python traceback |
| `agenteval replay --run missing.jsonl` error | raw `FileNotFoundError` Python traceback |
| `agenteval report --suite missing.json` error | raw `FileNotFoundError` Python traceback |
| README "Real results" date | `2026-09-27` (stale) |
| README EvalCore integration example | prose only, no code snippet |
| Tests for drift/replay/report missing-file handling | NONE |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 180 passed (+4) |
| `agenteval drift --a missing.json ...` error | `error: suite file not found for --a: 'missing.json'\nRun 'agenteval run --output <file>'...` |
| `agenteval replay --run missing.jsonl` error | `error: run file not found: 'missing.jsonl'\nCheck the path, or see examples/recordings/...` |
| `agenteval report --suite missing.json` error | `error: suite file not found: 'missing.json'\nRun 'agenteval run --output <file>'...` |
| README "Real results" date | `2026-09-28` (current) |
| README EvalCore integration example | YES — `## Integration with EvalCore` section with 3-command snippet |
| Tests for drift/replay/report missing-file handling | YES — `TestCLIErrorHandlingMissingFiles` (4 tests) |

### Evidence

Full test run:

```
$ cd /home/openclaw/portfolio/agent-eval-harness && .venv/bin/python -m pytest -q
........................................................................ [ 40%]
........................................................................ [ 80%]
....................................                                     [100%]
180 passed in 4.48s
```

Ruff clean:

```
$ .venv/bin/ruff check . && .venv/bin/ruff format --check . && echo "RUFF CLEAN"
All checks passed!
20 files already formatted
RUFF CLEAN
```

New error messages (before: raw traceback; after: actionable):

```
$ .venv/bin/agenteval drift --a nonexistent.json --b nonexistent2.json 2>&1; echo "Exit: $?"
error: suite file not found for --a: 'nonexistent.json'
Run 'agenteval run --output <file>' to generate a suite result first.
Exit: 1

$ .venv/bin/agenteval replay --run nonexistent.jsonl 2>&1; echo "Exit: $?"
error: run file not found: 'nonexistent.jsonl'
Check the path, or see examples/recordings/sample_run.jsonl for an example.
Exit: 1

$ .venv/bin/agenteval report --suite nonexistent.json 2>&1; echo "Exit: $?"
error: suite file not found: 'nonexistent.json'
Run 'agenteval run --output <file>' to generate a suite result first.
Exit: 1
```

New tests pass:

```
$ .venv/bin/python -m pytest tests/test_budget_drift.py::TestCLIErrorHandlingMissingFiles -v
tests/test_budget_drift.py::TestCLIErrorHandlingMissingFiles::test_drift_cli_missing_a PASSED
tests/test_budget_drift.py::TestCLIErrorHandlingMissingFiles::test_drift_cli_missing_b PASSED
tests/test_budget_drift.py::TestCLIErrorHandlingMissingFiles::test_replay_cli_missing_run PASSED
tests/test_budget_drift.py::TestCLIErrorHandlingMissingFiles::test_report_cli_missing_suite PASSED
4 passed in 0.32s
```

Demo still passes:

```
$ bash examples/run_demo.sh | grep -E "=== Demo complete|PASS: gate exits"
PASS: gate exits correctly (0 on good, 1 on regressed)
=== Demo complete ===
```

### Files changed

- `src/agenteval/cli.py` — `_cmd_replay`: wrapped `open(args.run)` in `try/except
  FileNotFoundError`; wrapped `Run.from_jsonl()` in `try/except (KeyError, ValueError)`;
  both print actionable error messages and return 1. `_cmd_drift`: wrapped `open(args.a)`
  and `open(args.b)` in separate pre-checks with actionable messages; wrapped `json.load()`
  in `try/except JSONDecodeError` for both. `_cmd_report`: wrapped `open(args.suite)` in
  `try/except FileNotFoundError` and `json.load()` in `try/except JSONDecodeError`.
- `README.md` — (1) "Real results" date: `2026-09-27` → `2026-09-28`. (2) Added
  `## Integration with EvalCore` section after the Inspect AI section: 3-command
  concrete snippet showing `evalcore run --cache replay` → `agenteval run` → `agenteval gate`,
  with a one-paragraph explanation of what each tool contributes.
- `tests/test_budget_drift.py` — updated module docstring to document the 4 new tests;
  added `TestCLIErrorHandlingMissingFiles` class (4 tests):
  `test_drift_cli_missing_a`, `test_drift_cli_missing_b`,
  `test_replay_cli_missing_run`, `test_report_cli_missing_suite`.
- `reports/improvements.md` — this entry

---



## c4-p08: Fix ADV2-3 (install URL unreproducible) — README source-install primary, git+ URL qualified (2026-09-28)

### Finding source

ADV2-3 (major, c2-p10-adversarial-1): README install instruction
`pip install git+https://github.com/AnnasMazhar/replayproof` is not reproducible —
`git ls-remote` fails authentication because the repo is private. Evidence from c2-p10:

```
$ git ls-remote https://github.com/AnnasMazhar/agent-eval-harness
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for 'https://github.com/AnnasMazhar/agent-eval-harness/'
```

Still open as of c4-p05 (not addressed by any prior improve pass). The finding was recorded
as "pending repo publish" but that is a deferral, not a fix — every person cloning the repo
to evaluate it sees a broken first command.

### Root cause

The Install section led with the git-URL form (`pip install git+...`) which requires the
repo to be publicly accessible. The source-install form (`git clone ... && pip install .`)
was listed as an "Or from source" fallback. Someone following the docs in the natural order
(primary form first) hit an authentication failure before reaching the fallback.

No test existed that would fail when a bare `pip install git+` command appeared without any
context indicating it requires public repo access.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 175 passed |
| README Install primary instruction | `pip install git+https://github.com/AnnasMazhar/replayproof` (fails if private) |
| README Install source path label | "Or from source" (secondary, buried) |
| Top-level quickstart note | "Install from the git URL above or from source" (ambiguous) |
| Test detecting bare git+ without availability note | NONE |
| ADV2-3 status | open (major) |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 176 passed (+1) |
| README Install primary instruction | `git clone ... && uv pip install -e '.[dev]'` (always works) |
| README git+ form placement | secondary, labelled "Once the repo is public, you can also install..." |
| Comment in git+ code block | `# Requires the repo to be publicly accessible:` on the line before the command |
| Top-level quickstart note | updated: "install from source as shown above ... if not yet public, see Install section" |
| Test detecting bare git+ without availability note | YES — `TestREADMEInstallContract.test_readme_git_url_install_has_availability_note` |
| ADV2-3 status | fixed |

### Evidence

Full test run:

```
$ cd /home/openclaw/portfolio/agent-eval-harness && .venv/bin/python -m pytest -q
........................................................................ [ 40%]
........................................................................ [ 81%]
................................                                         [100%]
176 passed in 5.15s
```

Ruff clean:

```
$ .venv/bin/ruff check . && .venv/bin/ruff format --check . && echo "RUFF CLEAN"
All checks passed!
20 files already formatted
RUFF CLEAN
```

New test verifies current README passes:

```
$ .venv/bin/python -m pytest tests/test_report.py::TestREADMEInstallContract -v
tests/test_report.py::TestREADMEInstallContract::test_readme_git_url_install_has_availability_note PASSED
1 passed in 0.19s
```

Fault injection (old README state — pip install git+ as primary with no preceding context):

```
$ python3 -c "
lines = ['## Install', '', '\`\`\`bash', 'pip install git+https://github.com/AnnasMazhar/replayproof', '\`\`\`']
notes = ('requires the repo to be publicly accessible', 'once the repo is public')
for i, line in enumerate(lines):
    if 'pip install git+' in line:
        window = lines[max(0, i-3):i]
        combined = ' '.join(l.lower() for l in window)
        print(f'Has note: {any(n in combined for n in notes)}')
"
Has note: False
```

The test assertion `assert not violations` fails for that README state (violations = [4]).

Demo still exits correctly:

```
$ bash examples/run_demo.sh | grep -E "=== Demo complete|PASS: gate exits"
PASS: gate exits correctly (0 on good, 1 on regressed)
=== Demo complete ===
```

### Files changed

- `README.md` — (1) Install section: reordered — source-install (`git clone` + `uv pip install
  -e '.[dev]'`) and plain pip variant are now primary; git-URL form is now secondary, preceded
  by "Once the repo is public..." prose and `# Requires the repo to be publicly accessible:`
  comment in the code block. (2) Top-level quickstart note: updated to reference "install from
  source as shown above" and direct to Install section for the offline path.
- `tests/test_report.py` — added `TestREADMEInstallContract` class (1 test):
  `test_readme_git_url_install_has_availability_note` — parses README.md, finds every
  `pip install git+` line, asserts that a qualifying availability note appears in the 3
  lines preceding it. Added fault description to module docstring.
- `reports/improvements.md` — this entry

---



## c3-p09: Fix four README credibility and usability gaps (2026-09-27)

### Finding source

Systematic audit of README.md against the actual CLI implementation and against
ADOPTION.md (which was corrected in c3-p03 with real Inspect log evidence). Four gaps
identified by reading what a stranger following the docs would encounter:

1. **BLOCKER — wrong CLI command in Inspect integration section:** README line 244
   `agenteval gate --baseline baseline.json --current recordings/my_eval_new.jsonl`
   passes a JSONL file as `--current`. The gate CLI calls `json.load()` on `--current`;
   it requires a JSON file produced by `agenteval run`. A JSONL file (newline-delimited
   JSON objects) raises `JSONDecodeError` and exits 1 with an error. A stranger following
   the docs hits a confusing error on the last command.

2. **CREDIBILITY — self-contradiction in Limitations:** The Limitations section said
   "v0.1 does not read Inspect `.eval` logs" with no mention of the bridge script. The
   `## Integration with Inspect AI` section above it shows a working bridge script that
   *does* convert `.eval` logs. A skeptical reviewer reading Limitations concludes the
   Inspect integration is broken, then scrolls up and sees the script — the contradiction
   undermines credibility.

3. **USABILITY — `agenteval record` has no PYTHONPATH note:** The recording section
   shows `agenteval record --agent examples.research_agent:research_agent` without any
   mention that a project-local agent module requires `PYTHONPATH=$(pwd)`. This hits as
   `ModuleNotFoundError: No module named 'examples'` for any non-installed agent
   package. ADOPTION.md documents this as FM-6 but the README did not.

4. **ROADMAP — "Inspect `.eval` log reader" listed as future work but bridge script
   already ships:** The Roadmap listed "Inspect `.eval` log reader" as a pending item,
   and `scripts/convert_inspect_log.py` is in the repo. The Roadmap item is accurate
   for a *native* reader (no conversion step), but listing the bare phrase left a
   reviewer unable to tell if the current state was "nothing exists" or "a bridge exists".

### Root causes

**Gap 1:** The Inspect integration CLI snippet was written before the CLI contract was
clarified. The `gate` command was documented as receiving a JSONL directly, bypassing
the `run` step. No test existed that would fail if a JSONL were passed as `--current`.

**Gap 2:** The Limitations section was written early and never updated when the Inspect
bridge was added. The two sections were maintained independently.

**Gap 3:** The recording section was adapted from the `agenteval record` implementation
pass without reference to the ADOPTION.md onboarding recipe, which documented the
PYTHONPATH issue after FM-6 was observed in the c3-p03 real execution.

**Gap 4:** The Roadmap was copied from the spec and never updated when `scripts/` gained
the bridge script.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 149 passed |
| README Inspect integration — gate command | `--current recordings/my_eval_new.jsonl` (wrong: JSONL not JSON) |
| `agenteval gate --current <jsonl>` test exists | NO |
| README Limitations — Inspect bridge mentioned | NO ("v0.1 does not read Inspect `.eval` logs") |
| README record section — PYTHONPATH note | NO |
| README Roadmap — Inspect entry | "Inspect `.eval` log reader" (ambiguous: no mention of existing bridge) |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 150 passed (+1) |
| README Inspect integration — gate command | corrected: `run` step produces `current.json`, gate takes that |
| `agenteval gate --current <jsonl>` test exists | YES — `TestGateCLIRejectsJSONL` |
| README Limitations — Inspect bridge mentioned | YES: "native reader not built-in; conversion script at `scripts/convert_inspect_log.py`" |
| README record section — PYTHONPATH note | YES — comment `PYTHONPATH=$(pwd) agenteval record ...` |
| README Roadmap — Inspect entry | Clarified: "Inspect `.eval` log reader (native, no conversion script required)" |

### Evidence

Full test run:

```
$ cd /home/openclaw/portfolio/agent-eval-harness && .venv/bin/python -m pytest -q
........................................................................ [ 48%]
........................................................................ [ 96%]
......                                                                   [100%]
150 passed in 2.75s
```

Ruff clean:

```
$ .venv/bin/ruff check . && .venv/bin/ruff format --check . && echo "RUFF CLEAN"
All checks passed!
20 files already formatted
RUFF CLEAN
```

New test (`TestGateCLIRejectsJSONL`):

```
$ .venv/bin/python -m pytest tests/test_budget_drift.py::TestGateCLIRejectsJSONL -v
tests/test_budget_drift.py::TestGateCLIRejectsJSONL::test_gate_cli_rejects_jsonl_as_current PASSED
1 passed in 0.21s
```

Demo still passes:

```
$ bash examples/run_demo.sh | grep -E "=== Demo complete|PASS: gate exits"
PASS: gate exits correctly (0 on good, 1 on regressed)
=== Demo complete ===
```

### Files changed

- `README.md` — (1) Inspect integration bash snippet: replaced `agenteval gate --current
  recordings/my_eval_new.jsonl` with a correct two-step sequence (`agenteval run` produces
  `current.json`, then `agenteval gate --current current.json`); (2) Limitations: updated
  Inspect entry to "v0.1 does not natively read Inspect `.eval` logs … conversion script
  included at `scripts/convert_inspect_log.py`"; (3) Recording section: added PYTHONPATH
  comment; (4) Roadmap: updated Inspect entry to "native, no conversion script required"
- `tests/test_budget_drift.py` — updated top docstring; added `TestGateCLIRejectsJSONL`
  class (1 test): `test_gate_cli_rejects_jsonl_as_current`
- `reports/improvements.md` — this entry

---

## c3-p08: Fix C2P11-MAJ-2 (gate accepts NaN/infinity) and C2P11-MAJ-1 (wilson_lower accepts negative confidence) (2026-09-27)

### Finding source

Adversarial review c2-p11 (cycle 2, adversarial pass 2). Two open major findings:

- **C2P11-MAJ-2 (headline):** `compare()` accepts NaN/infinity in current metrics and
  returns `ok=True`. A corrupted run file silently passes the gate. Root: NaN comparisons
  in Python return False for all orderings; `drop > threshold` is False when `drop` is NaN,
  so no gate ever trips. This inverts the gate's core safety property.
- **C2P11-MAJ-1:** `wilson_lower()` accepts negative confidence values without raising.
  `wilson_lower(3, 5, -0.5)` returned `0.733332` silently (meaningless value).

### Root causes

**C2P11-MAJ-2:** `compare()` extracted float metrics from the current dict with
`float(current.get("pass_rate", 0.0))` and used them in comparisons directly. Python's
IEEE 754 NaN semantics mean `float("nan") > 0.0 == False`, so the gate reported `ok=True`
for any current dict where pass_rate was NaN, effectively disabling the pass_rate gate.
Same problem for inf (which would incidentally trip, but the principle is wrong — non-finite
values must not enter the arithmetic at all).

**C2P11-MAJ-1:** `wilson_lower()` validated `successes` and `n` but not `confidence`.
A negative `confidence` is passed to `_normal_quantile((1 + confidence) / 2)`. For
`confidence=-0.5`, that's `_normal_quantile(0.25)` — a valid call that returns a negative
z-score. The Wilson formula then runs with a wrong z and produces a plausible-looking float.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 138 passed |
| `compare({'pass_rate': float('nan'), ...}, baseline).ok` | `True` (silent bypass — C2P11-MAJ-2) |
| `compare({'pass_rate': float('inf'), ...}, baseline).ok` | `True` (silent bypass — C2P11-MAJ-2) |
| `compare({'p95_latency_ms': float('nan'), ...}, baseline).ok` | `True` (silent bypass) |
| `wilson_lower(3, 5, -0.5)` | `0.733332` (garbage, no error — C2P11-MAJ-1) |
| `wilson_lower(3, 5, 0.0)` | returns float silently (invalid confidence) |
| `wilson_lower(3, 5, 1.5)` | returns float silently (invalid confidence) |
| Tests for NaN/inf gate rejection | NONE |
| Tests for confidence validation | NONE |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 149 passed (+11) |
| `compare({'pass_rate': float('nan'), ...}, baseline).ok` | `ValueError: current['pass_rate'] is not finite` |
| `compare({'pass_rate': float('inf'), ...}, baseline).ok` | `ValueError: current['pass_rate'] is not finite` |
| `compare({'p95_latency_ms': float('nan'), ...}, baseline).ok` | `ValueError: current['p95_latency_ms'] is not finite` |
| `wilson_lower(3, 5, -0.5)` | `ValueError: confidence must be in (0, 1), got -0.5` |
| `wilson_lower(3, 5, 0.0)` | `ValueError: confidence must be in (0, 1), got 0.0` |
| `wilson_lower(3, 5, 1.5)` | `ValueError: confidence must be in (0, 1), got 1.5` |
| Tests for NaN/inf gate rejection | YES — 4 tests in `TestGateNonFiniteRejection` |
| Tests for confidence validation | YES — 7 tests in `TestWilsonLowerConfidenceValidation` |

### Evidence

```
$ cd /home/openclaw/portfolio/agent-eval-harness && .venv/bin/python -m pytest -q
........................................................................ [ 48%]
........................................................................ [ 96%]
.....                                                                    [100%]
149 passed in 14.95s
```

```
$ .venv/bin/ruff check . && .venv/bin/ruff format --check . && echo "RUFF CLEAN"
All checks passed!
20 files already formatted
RUFF CLEAN
```

NaN gate rejection (C2P11-MAJ-2 fix):

```
$ .venv/bin/python -c "
from agenteval.budget import compare, Baseline
import math
baseline = Baseline({'pass_rate': 0.9, 'total_tokens_in': 100, 'total_tokens_out': 100,
    'p95_latency_ms': 100.0, 'total_cost_usd': 0.0})
for name, val in [('nan', float('nan')), ('inf', float('inf'))]:
    try:
        compare({'pass_rate': val, 'total_tokens_in': 100, 'total_tokens_out': 100,
                 'p95_latency_ms': 100.0, 'total_cost_usd': 0.0}, baseline)
        print(f'FAIL {name}: no error raised (gate bypassed)')
    except ValueError as e:
        print(f'PASS {name}: ValueError raised: {e}')
"
PASS nan: ValueError raised: current['pass_rate'] is not finite (nan); corrupted run files must not be passed to the gate
PASS inf: ValueError raised: current['pass_rate'] is not finite (inf); corrupted run files must not be passed to the gate
```

Confidence validation (C2P11-MAJ-1 fix):

```
$ .venv/bin/python -c "
from agenteval.scoring import wilson_lower
for conf, desc in [(-0.5, 'negative'), (0.0, 'zero'), (1.0, 'one'), (1.5, 'gt one'), (0.95, 'valid')]:
    try:
        result = wilson_lower(3, 5, conf)
        print(f'PASS {desc} ({conf}): result={result:.4f}')
    except ValueError as e:
        print(f'PASS {desc} ({conf}): ValueError: {e}')
"
PASS negative (-0.5): ValueError: confidence must be in (0, 1), got -0.5
PASS zero (0.0): ValueError: confidence must be in (0, 1), got 0.0
PASS one (1.0): ValueError: confidence must be in (0, 1), got 1.0
PASS gt one (1.5): ValueError: confidence must be in (0, 1), got 1.5
PASS valid (0.95): result=0.2307
```

New tests for C2P11-MAJ-2 (`TestGateNonFiniteRejection`):

```
$ .venv/bin/python -m pytest -q tests/test_budget_drift.py::TestGateNonFiniteRejection -v
tests/test_budget_drift.py::TestGateNonFiniteRejection::test_compare_rejects_nan_pass_rate PASSED
tests/test_budget_drift.py::TestGateNonFiniteRejection::test_compare_rejects_inf_pass_rate PASSED
tests/test_budget_drift.py::TestGateNonFiniteRejection::test_compare_rejects_nan_latency PASSED
tests/test_budget_drift.py::TestGateNonFiniteRejection::test_compare_rejects_inf_cost PASSED
4 passed in 0.36s
```

New tests for C2P11-MAJ-1 (`TestWilsonLowerConfidenceValidation`):

```
$ .venv/bin/python -m pytest -q tests/test_scoring.py::TestWilsonLowerConfidenceValidation -v
tests/test_scoring.py::TestWilsonLowerConfidenceValidation::test_wilson_lower_rejects_negative_confidence PASSED
tests/test_scoring.py::TestWilsonLowerConfidenceValidation::test_wilson_lower_rejects_small_negative_confidence PASSED
tests/test_scoring.py::TestWilsonLowerConfidenceValidation::test_wilson_lower_rejects_zero_confidence PASSED
tests/test_scoring.py::TestWilsonLowerConfidenceValidation::test_wilson_lower_rejects_confidence_one PASSED
tests/test_scoring.py::TestWilsonLowerConfidenceValidation::test_wilson_lower_rejects_confidence_gt_one PASSED
tests/test_scoring.py::TestWilsonLowerConfidenceValidation::test_wilson_lower_accepts_095_confidence PASSED
tests/test_scoring.py::TestWilsonLowerConfidenceValidation::test_wilson_lower_accepts_099_confidence PASSED
7 passed in 0.28s
```

Demo still passes:

```
$ bash examples/run_demo.sh | grep -E "=== Demo complete|PASS: gate exits"
PASS: gate exits correctly (0 on good, 1 on regressed)
=== Demo complete ===
```

### Files changed

- `src/agenteval/budget.py` — added `import math`; added non-finite guard at start of
  `compare()` for `pass_rate`, `p95_latency_ms`, `total_cost_usd`; updated module
  docstring to document the fail-closed semantics
- `src/agenteval/scoring.py` — added `if not (0.0 < confidence < 1.0): raise ValueError`
  guard in `wilson_lower()` before calling `_normal_quantile`
- `tests/test_budget_drift.py` — updated module docstring; added `TestGateNonFiniteRejection`
  class (4 tests): `test_compare_rejects_nan_pass_rate`, `test_compare_rejects_inf_pass_rate`,
  `test_compare_rejects_nan_latency`, `test_compare_rejects_inf_cost`
- `tests/test_scoring.py` — updated module docstring; added `TestWilsonLowerConfidenceValidation`
  class (7 tests) covering negative, zero, ≥1 confidence values, and boundary 0.95/0.99
- `reports/improvements.md` — this entry

---



## c2-p09: Fix ADOPTION.md broken contract examples, README Contract YAML sync, COMPARISONS star count (2026-09-27)

### Finding source

Audit of ADOPTION.md against `src/agenteval/assertions.py` — the biggest credibility gap
a skeptical reviewer would find: the adoption guide is broken for anyone who follows it.

Two contract examples in ADOPTION.md raise `TypeError` when passed to `_build_check()`:

1. **cs-002 `tool_sequence`**: uses `tools:` but `ToolSequenceCheck.__init__()` requires
   `expected:`. Error: `ToolSequenceCheck.__init__() got an unexpected keyword argument 'tools'`
2. **cs-005 `no_pattern`**: uses `field: content` but `NoPatternCheck.__init__()` requires
   `field_name:`. Error: `NoPatternCheck.__init__() got an unexpected keyword argument 'field'`
   Also present in the FM-3 "fix" example block (ADOPTION.md line 373).

Secondary credibility issues fixed in the same pass:
- README "Real results" date: `2026-09-26` → `2026-09-27` (demo was regenerated on Sep 27)
- README Contract YAML section: example lacked `id` and `severity` fields, inconsistent
  with the actual `examples/contracts/research.yaml`. Updated to match the real file.
- COMPARISONS.md star count for promptfoo: `25,477` → `25,482` (RESEARCH.md had 25,482
  from the same GitHub API fetch; COMPARISONS.md had a stale earlier number).

### Root causes

**Broken ADOPTION.md contracts:** The ADOPTION.md customer_service.yaml was written during
the c1-p09 improve pass as a documentation example. At the time, the parameter names
were not cross-checked against the `@dataclass` field names in `assertions.py`.
`ToolSequenceCheck` uses `expected` (per the spec), not `tools`. `NoPatternCheck` uses
`field_name` (per the code), not `field`.

**README Contract YAML:** The README example was a simplified illustration and was not
regenerated from the actual `examples/contracts/research.yaml` file after that file was
updated in c1-p09 to add explicit `id` and `severity` fields.

**COMPARISONS.md star count drift:** The two files are maintained independently and the
promptfoo count was updated in RESEARCH.md (via GitHub API re-fetch in c2-p02) but the
COMPARISONS.md table was not updated in the same pass.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 133 passed |
| ADOPTION.md cs-002 tool_sequence parameter | `tools:` (raises TypeError) |
| ADOPTION.md cs-005 no_pattern parameter | `field: content` (raises TypeError) |
| ADOPTION.md FM-3 fix no_pattern parameter | `field: content` (raises TypeError) |
| README Contract YAML has `id` / `severity` | NO (missing, inconsistent with real file) |
| README "Real results" date | 2026-09-26 (stale) |
| COMPARISONS.md promptfoo stars | 25,477 (stale) |
| Tests catching ADOPTION.md parameter bugs | NONE |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 136 passed (+3) |
| ADOPTION.md cs-002 tool_sequence parameter | `expected:` (correct, no error) |
| ADOPTION.md cs-005 no_pattern parameter | `field_name: final_content` (correct) |
| ADOPTION.md FM-3 fix no_pattern parameter | `field_name: final_content` (correct) |
| README Contract YAML has `id` / `severity` | YES — matches actual `research.yaml` |
| README "Real results" date | 2026-09-27 |
| COMPARISONS.md promptfoo stars | 25,482 (consistent with RESEARCH.md) |
| Tests catching ADOPTION.md parameter bugs | YES — 3 new tests in `TestAdoptionGuideContracts` |

### Evidence

All ADOPTION.md contract checks pass after fix:

```
$ python3 -c "
from agenteval.assertions import _build_check
checks = [
    {'type': 'required_tools', 'id': 'cs-001', 'severity': 'error', 'description': 'required', 'names': ['search_knowledge_base']},
    {'type': 'tool_sequence', 'id': 'cs-002', 'severity': 'error', 'description': 'sequence', 'expected': ['search_knowledge_base'], 'ordered': True},
    {'type': 'forbidden_tools', 'id': 'cs-003', 'severity': 'warn', 'description': 'forbidden', 'names': ['get_internal_debug_info']},
    {'type': 'arg_schema', 'id': 'cs-004', 'severity': 'error', 'description': 'schema', 'tool': 'search_knowledge_base', 'schema': {'type': 'object', 'required': ['query'], 'properties': {'query': {'type': 'string', 'minLength': 1}}}},
    {'type': 'no_pattern', 'id': 'cs-005', 'severity': 'error', 'description': 'email', 'field_name': 'final_content', 'regex': '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'},
    {'type': 'max_tool_calls', 'id': 'cs-006', 'severity': 'warn', 'description': 'max calls', 'n': 8},
    {'type': 'max_tokens', 'id': 'cs-007', 'severity': 'warn', 'description': 'max tokens', 'n': 4000},
]
for c in checks:
    try:
        obj = _build_check(c)
        print(f'OK: {c[\"id\"]}')
    except Exception as e:
        print(f'FAIL: {c[\"id\"]}: {e}')
"
OK: cs-001
OK: cs-002
OK: cs-003
OK: cs-004
OK: cs-005
OK: cs-006
OK: cs-007
```

Full test run:

```
$ pytest -q
........................................................................[52%]
................................................................        [100%]
136 passed in 2.65s
```

Ruff clean:

```
$ ruff check . && ruff format --check . && echo "RUFF CLEAN"
All checks passed!
19 files already formatted
RUFF CLEAN
```

New tests added (`TestAdoptionGuideContracts`):

```
$ pytest -q tests/test_assertions.py::TestAdoptionGuideContracts -v
tests/test_assertions.py::TestAdoptionGuideContracts::test_adoption_customer_service_yaml_parses PASSED
tests/test_assertions.py::TestAdoptionGuideContracts::test_adoption_tool_sequence_expected_field PASSED
tests/test_assertions.py::TestAdoptionGuideContracts::test_adoption_no_pattern_field_name PASSED
3 passed in 0.22s
```

Demo still passes:

```
$ bash examples/run_demo.sh | grep -E "=== Demo complete|PASS: gate exits"
PASS: gate exits correctly (0 on good, 1 on regressed)
=== Demo complete ===
```

### Files changed

- `docs/ADOPTION.md` — cs-002: `tools:` → `expected:`; cs-005: `field: content` →
  `field_name: final_content`; FM-3 fix block: same `field: content` → `field_name: final_content`
- `README.md` — Contract YAML section: added explicit `id` and `severity` fields to match
  real `examples/contracts/research.yaml`; "Real results" date: `2026-09-26` → `2026-09-27`
- `COMPARISONS.md` — promptfoo star count: `25,477` → `25,482` (consistent with RESEARCH.md)
- `tests/test_assertions.py` — added `TestAdoptionGuideContracts` class (3 tests):
  `test_adoption_customer_service_yaml_parses`, `test_adoption_tool_sequence_expected_field`,
  `test_adoption_no_pattern_field_name`; updated top docstring to include the new class
- `reports/improvements.md` — this entry

---



## c2-p08: Fix AR-MAJ-1 (PyPI name collision), AR-MAJ-3 (timestamp test), AR2-MAJ-4 (gate zero-baseline bypass), AR2-MIN-2 (wilson_lower invalid input) (2026-09-27)

### Finding source

Four findings from the cycle-1 adversarial review:
- AR-MAJ-1 (`c1-p10`): `pip install agent-eval-harness` installs a third-party package (Franck Ndzomga). The PyPI name `agent-eval-harness` is occupied. False claim in the top 5 lines of README.
- AR-MAJ-3 (`c1-p10`): `test_markdown_no_timestamps` does not fail on its named fault. Regex only matched ISO-T form (`2026-09-27T12:34:56`); `datetime.now()` renders with a space separator (`2026-09-27 12:34:56.789`) and bypassed the check.
- AR2-MAJ-4 (`c1-p11`): Gate zero-baseline bypass silently disables token/latency/cost gates. A run consuming 2M tokens and $1000 passed against a zero baseline with `ok=True` and no indication that three gates were skipped.
- AR2-MIN-2 (`c1-p11`): `wilson_lower(10, 5)` accepted invalid input (successes > n) and returned 1.0 silently.

### Root causes

**AR-MAJ-1:** `pyproject.toml` had `name = "agent-eval-harness"` — an occupied PyPI slot. README showed `pip install agent-eval-harness` twice (lines 15 and 48). The repo's correct positioning name per MARKET-VERDICTS is `replayproof`.

**AR-MAJ-3:** The test regex `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}` requires the ISO-T separator. The fault injection used `str(datetime.now())` which produces `2026-09-27 11:06:01.789012` (space, microseconds). The test docstring claimed it caught `2026-09-26` and `12:34:56` patterns — those claims were false.

**AR2-MAJ-4:** `compare()` silently skipped percentage gates when baseline values were zero (to avoid division by zero), but did not record which gates were skipped. `GateReport` had no `skipped_zero_baseline` field.

**AR2-MIN-2:** `wilson_lower()` had no input validation on the range of `successes`. A value of `successes > n` is physically impossible and the function should fail-closed.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 125 passed |
| `pyproject.toml` distribution name | `agent-eval-harness` (PyPI-occupied) |
| README install instruction | `pip install agent-eval-harness` (false) |
| `test_markdown_no_timestamps` catches `datetime.now()` injection | NO — test passed with fault active |
| `GateReport` surfaces skipped zero-baseline gates | NO — no `skipped_zero_baseline` field |
| `compare(huge_tokens, zero_baseline).ok` | True with no warning (silent bypass) |
| `wilson_lower(10, 5)` | Returns 1.0 silently (invalid input accepted) |
| `wilson_lower(-1, 5)` | Returns nonsensical value silently |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 133 passed (+8) |
| `pyproject.toml` distribution name | `replayproof` |
| README install instruction | `pip install git+https://github.com/AnnasMazhar/agent-eval-harness` + note explaining PyPI collision |
| `test_markdown_no_timestamps` catches `datetime.now()` injection | YES — broadened regex catches both `\d{4}-\d{2}-\d{2}` and `\d{2}:\d{2}:\d{2}` |
| `GateReport` surfaces skipped zero-baseline gates | YES — `skipped_zero_baseline: tuple[str, ...]` field + `to_dict()` includes it |
| `compare(huge_tokens, zero_baseline)` output | `ok=True, skipped_zero_baseline=['total_tokens', 'p95_latency_ms', 'total_cost_usd']` |
| CLI gate output surfaces skipped gates | YES — Warning line printed when any gate is skipped |
| `wilson_lower(10, 5)` | Raises `ValueError: successes (10) must be <= n (5)` |
| `wilson_lower(-1, 5)` | Raises `ValueError: successes must be >= 0, got -1` |

### Evidence

```
$ cd /build/portfolio/agent-eval-harness && source .venv/bin/activate && pytest -q
........................................................................ [ 54%]
.............................................................            [100%]
133 passed in 2.64s
```

```
$ ruff check . && ruff format --check . && echo "RUFF CLEAN"
All checks passed!
19 files already formatted
RUFF CLEAN
```

```
$ python3 -c "import agenteval; print(agenteval.__version__)"
0.1.0
```

```
$ agenteval --help | head -3
usage: agenteval [-h] [--version] {record,replay,run,gate,drift,report} ...

Deterministic, offline-replayable regression testing for LLM agents.
```

Zero-baseline gate bypass now surfaced (AR2-MAJ-4):

```
$ source .venv/bin/activate && agenteval run \
    --contract examples/contracts/research.yaml \
    --runs examples/recordings/sample_run.jsonl \
    --output /tmp/sample_result.json \
  && agenteval gate --baseline /tmp/sample_result.json --current /tmp/sample_result.json
Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero (first-run or corrupted baseline): total_tokens, total_cost_usd
```

Timestamp fault injection now caught (AR-MAJ-3):

```
Injected output contains date pattern? True ['2026-09-27']
Injected output contains time pattern? True ['11:06:01']
PASS: the broadened test WOULD catch this fault (assertion would fail in pytest)
```

wilson_lower input validation (AR2-MIN-2):

```
PASS: raises ValueError for successes>n: successes (10) must be <= n (5); received more successes than total trials
PASS: raises ValueError for negative successes: successes must be >= 0, got -1
PASS: wilson_lower(0, 10) = 0.0000
PASS: wilson_lower(5, 5) = 0.5655
```

Demo still exits correctly:

```
$ bash examples/run_demo.sh
...
--- Step 3: gate good run vs itself (expect: PASS, exit 0) ---
Gate: PASS — no regressions detected.
Warning: the following gates were not enforced because the baseline value is zero (first-run or corrupted baseline): total_tokens, total_cost_usd
Exit code: 0

--- Step 4: gate regressed run vs good baseline (expect: FAIL, exit 1) ---
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
Warning: the following gates were not enforced ...
Exit code: 1
...
PASS: gate exits correctly (0 on good, 1 on regressed)
=== Demo complete ===
```

### Files changed

- `pyproject.toml` — distribution `name` changed from `agent-eval-harness` to `replayproof`
- `README.md` — replaced both `pip install agent-eval-harness` with `pip install git+https://github.com/AnnasMazhar/agent-eval-harness`; added note explaining PyPI name collision; moved "No API keys" claim to "What problem this solves"
- `src/agenteval/budget.py` — added `skipped_zero_baseline: tuple[str, ...]` field to `GateReport`; `compare()` now records skipped gates in `skipped_zero_baseline`; `to_dict()` includes the field; module docstring explains zero-baseline semantics
- `src/agenteval/cli.py` — `_cmd_gate` prints a Warning line when `skipped_zero_baseline` is non-empty
- `src/agenteval/scoring.py` — `wilson_lower()` validates `successes >= 0` and `successes <= n` before proceeding; added `import pytest` to fix test imports
- `tests/test_report.py` — `test_markdown_no_timestamps` regex broadened from ISO-T pattern to separate `\d{4}-\d{2}-\d{2}` and `\d{2}:\d{2}:\d{2}` patterns matching the test docstring's claim
- `tests/test_budget_drift.py` — added `TestGateZeroBaselineSurfaces` class with 4 new tests for AR2-MAJ-4
- `tests/test_scoring.py` — added `import pytest`; added `TestWilsonLowerInputValidation` class with 4 new tests for AR2-MIN-2
- `reports/improvements.md` — this entry

---



## c1-p09: Fix contract/README mismatch, error messages, record command (2026-09-27)

### Finding source

Adversarial inspection of README vs filesystem: the README Contract YAML section showed
`forbidden_tools: [send_email]` but the actual `examples/contracts/research.yaml` had no
such check. Any reviewer who ran the demo and compared the README example to the real file
would find an immediate discrepancy.

Secondary findings from error-message testing:
- `FileNotFoundError`, `KeyError: 'name'`, and YAML `ScannerError` all dumped raw Python
  tracebacks — not actionable for a stranger cloning the repo.
- `agenteval record` printed "Not yet wired to a live agent in this demo build" — a stub
  that makes the tool look incomplete when the real implementation is simple.
- Total Tokens = 0 in the real results table had no explanation — looks like a bug.

### Root cause

The contract YAML in the README was written to illustrate the full feature set
(`forbidden_tools`, etc.) but the actual file was created independently without syncing.
The CLI had no error handling wrappers, so any input mistake produced a traceback.
The `record` command was left as a stub after the implementation pass.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 113 passed |
| `examples/contracts/research.yaml` has `forbidden_tools` | NO (mismatch with README) |
| README contract example matches actual contract | NO |
| `agenteval record` works | NO (stub: "Not yet wired") |
| Bad inputs produce actionable errors | NO (raw tracebacks) |
| Total Tokens = 0 explained in README | NO |
| Inspect AI integration example in README | NO |
| `agenteval run --contract nonexistent.yaml` error message | raw FileNotFoundError traceback |
| `agenteval run --runs bad.jsonl` error message | raw KeyError: 'name' traceback |
| `agenteval gate --baseline nonexistent.json` error message | raw FileNotFoundError traceback |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 113 passed (no regressions) |
| `examples/contracts/research.yaml` has `forbidden_tools` | YES — `names: [send_email]` |
| README contract example matches actual contract | YES — identical |
| `agenteval record` works | YES — loads module, calls `build_tools()` factory, writes JSONL |
| Bad inputs produce actionable errors | YES — all 5 error paths give specific fix hints |
| Total Tokens = 0 explained in README | YES — explicit note in Real results section |
| Inspect AI integration example in README | YES — `## Integration with Inspect AI` section |
| `agenteval run --contract nonexistent.yaml` error message | `error: contract file not found: 'nonexistent.yaml'\nCheck the path, or see examples/contracts/research.yaml for a template.` |
| `agenteval run --runs bad.jsonl` error message | `error: cannot parse run on line 1 of 'bad_run.jsonl': 'name'\nEach line must be a JSON object with at least 'name', 'turns', and 'schema_version' fields.` |
| `agenteval gate --baseline nonexistent.json` error message | `error: baseline file not found: 'nonexistent.json'\nRun 'agenteval run --output <baseline_file>' on a known-good run and commit it.` |

### Evidence

```
$ cd /build/portfolio/agent-eval-harness && source .venv/bin/activate && pytest -q
........................................................................ [ 63%]
.........................................                                [100%]
113 passed in 2.68s
```

```
$ ruff check . && ruff format --check . && echo "RUFF CLEAN"
All checks passed!
19 files already formatted
RUFF CLEAN
```

```
$ agenteval run --contract nonexistent.yaml --runs examples/recordings/sample_run.jsonl
error: contract file not found: 'nonexistent.yaml'
Check the path, or see examples/contracts/research.yaml for a template.
```

```
$ echo '{"broken": true}' > /tmp/bad_run.jsonl && \
  agenteval run --contract examples/contracts/research.yaml --runs /tmp/bad_run.jsonl
error: cannot parse run on line 1 of '/tmp/bad_run.jsonl': 'name'
Each line must be a JSON object with at least 'name', 'turns', and 'schema_version' fields. See examples/recordings/sample_run.jsonl.
```

```
$ PYTHONPATH=. agenteval record \
    --agent examples.research_agent:research_agent \
    --task "How do solar panels work" \
    --output /tmp/recorded_run.jsonl
Recorded run: 'How do solar panels work'
  turns       : 2
  tool calls  : 2
  output      : /tmp/recorded_run.jsonl
```

```
$ bash examples/run_demo.sh
=== agent-eval-harness demo ===
...
--- Step 4: gate regressed run vs good baseline (expect: FAIL, exit 1) ---
Gate: FAIL — regressions detected:
Metric                        Baseline      Current    Threshold
-----------------------------------------------------------------
pass_rate                       1.0000       0.5000       0.0000
Exit code: 1
...
PASS: gate exits correctly (0 on good, 1 on regressed)
=== Demo complete ===
```

### Files changed

- `examples/contracts/research.yaml` — added `forbidden_tools: [send_email]`, corrected contract name from `research_contract` to `research`
- `src/agenteval/cli.py` — wired `record` command (was stub); added actionable error handling to `run`, `gate` for `FileNotFoundError`, `KeyError`, `YAMLError`, `JSONDecodeError`
- `README.md` — added token=0 explanation note; fixed quickstart (two-step evaluate then gate); added `## Integration with Inspect AI` section with Inspect bridge script; added `## Recording your own agent` section; confirmed contract YAML now matches actual file
- `reports/improvements.md` — this file

---

## c1-p08: Fix wilson_lower(5, 5) wrong value in docs (2026-09-27)

### Finding source

Spec `agent-eval-harness.md` RESEARCH CORRECTIONS, Tier 2 item 10:

> `wilson_lower(5, 5) ≈ 0.478` is **wrong — the actual value is 0.566**.
> Off by ~9 percentage points.

Confirmed by adversarial review finding F3 (ADVERSARIAL_REVIEW.md line 258), which itself
states `wilson_lower(5, 5) = 0.478` — meaning the reviewer also copied the wrong value
rather than running the code.

### Root cause

`docs/RESEARCH.md` section F-1 (falsification) stated `wilson_lower(5, 5, 0.95) ≈ 0.478`
(4 occurrences). No test existed for this specific input, so the error persisted through
two eval passes and an adversarial review undetected.

The actual formula for p_hat = 1.0 simplifies cleanly:
- term_under_root = 0 + z²/(4n²); sqrt(...) = z/(2n)
- numerator = 1.0 + z²/(2n) - z·z/(2n) = 1.0
- denominator = 1 + z²/n
- lower = 1 / (1 + z²/n) = 1 / (1 + 3.8416/5) = 1 / 1.7683 = **0.5655**

The wrong value 0.478 would arise from using z = 1.64 (one-sided 95%) instead of
z = 1.96 (two-sided), or from a denominator error — both detectable by the new KAT.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 112 passed |
| wilson_lower(5,5) documented value | 0.478 (wrong) |
| Files with wrong value | RESEARCH.md (×4), ADVERSARIAL_REVIEW.md (×1) |
| KAT for n=5 input | none |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 113 passed (+1) |
| wilson_lower(5,5) documented value | 0.5655 (correct) |
| Files with wrong value | 0 |
| KAT for n=5 input | test_wilson_lower_n5_s5 (catches any implementation returning <0.5 or ~0.478) |

### Evidence

```
$ cd /build/portfolio/agent-eval-harness && source .venv/bin/activate && pytest -q
........................................................................ [ 63%]
.........................................                                [100%]
113 passed in 3.35s
```

```
$ ruff check . && ruff format --check . && echo "RUFF CLEAN"
All checks passed!
19 files already formatted
RUFF CLEAN
```

```
$ python3 -c "from agenteval.scoring import wilson_lower; print(f'wilson_lower(5,5) = {wilson_lower(5,5,0.95):.4f}')"
wilson_lower(5,5) = 0.5655
```

### Files changed

- `tests/test_scoring.py` — added `test_wilson_lower_n5_s5` KAT with hand computation
- `docs/RESEARCH.md` — corrected 4 occurrences of 0.478 → 0.5655 with correction note
- `docs/ADVERSARIAL_REVIEW.md` — corrected F3 finding; status changed to Fixed
- `reports/improvements.md` — this file

### Finding source

Spec `agent-eval-harness.md` RESEARCH CORRECTIONS, Tier 2 item 10:

> `wilson_lower(5, 5) ≈ 0.478` is **wrong — the actual value is 0.566**.
> Off by ~9 percentage points.

Confirmed by adversarial review finding F3 (ADVERSARIAL_REVIEW.md line 258), which itself
states `wilson_lower(5, 5) = 0.478` — meaning the reviewer also copied the wrong value
rather than running the code.

### Root cause

`docs/RESEARCH.md` section F-1 (falsification) stated `wilson_lower(5, 5, 0.95) ≈ 0.478`
(4 occurrences). No test existed for this specific input, so the error persisted through
two eval passes and an adversarial review undetected.

The actual formula for p_hat = 1.0 simplifies cleanly:
- term_under_root = 0 + z²/(4n²); sqrt(...) = z/(2n)
- numerator = 1.0 + z²/(2n) - z·z/(2n) = 1.0
- denominator = 1 + z²/n
- lower = 1 / (1 + z²/n) = 1 / (1 + 3.8416/5) = 1 / 1.7683 = **0.5655**

The wrong value 0.478 would arise from using z = 1.64 (one-sided 95%) instead of
z = 1.96 (two-sided), or from a denominator error — both detectable by the new KAT.

### Before

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 112 passed |
| wilson_lower(5,5) documented value | 0.478 (wrong) |
| Files with wrong value | RESEARCH.md (×4), ADVERSARIAL_REVIEW.md (×1) |
| KAT for n=5 input | none |

### After

| Metric | Value |
| ------ | ----- |
| Tests (pytest) | 113 passed (+1) |
| wilson_lower(5,5) documented value | 0.5655 (correct) |
| Files with wrong value | 0 |
| KAT for n=5 input | test_wilson_lower_n5_s5 (catches any implementation returning <0.5 or ~0.478) |

### Evidence

```
$ cd /build/portfolio/agent-eval-harness && source .venv/bin/activate && pytest -q
........................................................................ [ 63%]
.........................................                                [100%]
113 passed in 3.35s
```

```
$ ruff check . && ruff format --check . && echo "RUFF CLEAN"
All checks passed!
19 files already formatted
RUFF CLEAN
```

```
$ python3 -c "from agenteval.scoring import wilson_lower; print(f'wilson_lower(5,5) = {wilson_lower(5,5,0.95):.4f}')"
wilson_lower(5,5) = 0.5655
```

### Files changed

- `tests/test_scoring.py` — added `test_wilson_lower_n5_s5` KAT with hand computation
- `docs/RESEARCH.md` — corrected 4 occurrences of 0.478 → 0.5655 with correction note
- `docs/ADVERSARIAL_REVIEW.md` — corrected F3 finding; status changed to Fixed
- `reports/improvements.md` — this file
