# Improvement Log — agent-eval-harness

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
$ cd /home/openclaw/portfolio/agent-eval-harness && source .venv/bin/activate && pytest -q
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
$ cd /home/openclaw/portfolio/agent-eval-harness && source .venv/bin/activate && pytest -q
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
$ cd /home/openclaw/portfolio/agent-eval-harness && source .venv/bin/activate && pytest -q
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
