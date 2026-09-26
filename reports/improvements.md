# Improvement Log — agent-eval-harness

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
