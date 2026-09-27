# Improvement Log — agent-eval-harness

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
