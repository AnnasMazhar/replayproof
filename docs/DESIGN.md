# DESIGN.md — One-page design rationale

## Why record/replay beats live evals

Live evals require API keys, cost money per run, and are non-deterministic: the same
agent on the same input may produce different tool calls on different runs depending on
LLM temperature, provider load, and API version. This means CI cannot distinguish a
genuine regression from sampling variance.

Record/replay separates the two concerns:
- **Recording** happens once, with a real LLM, producing a JSONL file.
- **Replay** runs in CI offline, testing only the deterministic scaffold — tool routing,
  argument handling, contract evaluation — not the LLM's sampling behaviour.

A passing replay proves the scaffold is correct. A failing replay proves a regression in
the scaffold. Neither claim requires a live LLM call.

This design is validated by Mudasiru (2026, arxiv 2607.16200), which reports F=1.0 replay
fidelity and 98.3% latency reduction for tool-calling agents in dry mode.

## Statistics choices

**Wilson score interval**, not the Wald interval. The Wald interval
`p_hat +/- z*sqrt(p_hat*(1-p_hat)/n)` is taught first and implemented everywhere, but
it undercovers near p=0 and p=1 (the precise regime where CI eval suites operate).
Wilson's interval inverts the score test and has better coverage for all n and p.

The gate uses the **lower bound** of the Wilson interval, not the point estimate. For a
suite with 4/4 passing (100% observed rate), the Wilson lower bound at 95% is 51%.
This prevents false confidence from small suites and is conservative by design.

Reference: Wilson (1927), JASA 22(158):209-212; D'Oro et al. (2026), arxiv 2605.08261.

## Failure modes this harness catches

1. **Regression in tool routing**: agent stops calling a required tool — caught by
   `required_tools` and `tool_sequence` checks.
2. **Argument schema drift**: agent passes malformed args — caught by `arg_schema`.
3. **PII leakage**: agent emits an email or SSN in its final answer — caught by
   `no_pattern` with `PII_PATTERNS`.
4. **Token budget creep**: model update causes 50% more tokens per call — caught by
   the token gate in `budget.py`.
5. **Silent agent failure**: agent returns empty string — caught by `final_answer_not_empty`.
6. **Model swap regression**: two models produce different tool call verdicts — detected
   by `drift.py` and classified as regression vs fix vs churn.

## What it does not catch

- Semantic correctness of the final answer (requires judge-based scoring, not in v0.1).
- Non-deterministic LLM output (by design — dry replay freezes LLM output).
- Regressions that only appear at the response quality level (tone, factuality).
