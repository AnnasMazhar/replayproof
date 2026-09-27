# Improvement Log — agent-eval-harness

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
