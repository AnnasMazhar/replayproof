# COMPARISONS — where replayproof fits, and where it does not

Every cell below was checked against the tool's own documentation or repository on
**2026-09-28** (last full refresh: c6-p02-research-2, 21:31 UTC). Nothing here is
inferred from marketing copy. Where a capability was not found in a tool's docs, the
cell says so rather than guessing. Star counts and release dates are point-in-time from
the GitHub API and PyPI; they drift.

**Position claim (the only one):** a layer over recorded runs that answers three
questions an eval runner does not — which tool-call contract broke, what the pass rate
is with a 95% Wilson lower bound instead of a bare percentage, and whether token cost or
latency regressed against a stored baseline.

## Point-in-time facts (fetched 2026-09-28, 21:31 UTC)

| Tool | Licence | Stars | Version / release |
|---|---|---|---|
| EvalCore (`eval-core/evalcore`) | Apache-2.0 | 16 | v0.7.5 released 2026-07-19; Rust, pre-1.0; **64 days inactive** |
| inspect_ai (`UKGovernmentBEIS/inspect_ai`) | MIT | **2,875** | PyPI **0.3.272** published **2026-09-28** |
| inspect-replay (`repowazdogz-droid/inspect-replay`) | MIT | 0 | v0.2.0 (2026-07-14); not on PyPI; **77 days inactive** |
| inspect-mlflow (`debu-sinha/inspect-mlflow`) | MIT | 3 | PyPI 0.8.1 published 2026-09-15 |
| DeepEval (`confident-ai/deepeval`) | Apache-2.0 | **18,489** | 4.2.6 published 2026-09-24 |
| promptfoo (`promptfoo/promptfoo`) | MIT (OpenAI) | **25,537** | 0.123.1 released 2026-09-18 |
| Braintrust (`braintrustdata/braintrust-sdk-python`) | SaaS / MIT SDK | 20 (SDK) | Python SDK v0.42.0 (2026-09-22) |
| LangSmith (`langchain-ai/langsmith-sdk`) | SaaS / MIT SDK | 1,064 (SDK) | Python SDK v0.14.1 (2026-09-25) |
| AgentOps (`AgentOps-AI/agentops`) | MIT | **5,846** | 0.4.21; cloud-first monitoring; **95 days inactive** |
| Arize Phoenix (`Arize-ai/phoenix`) | Apache-2.0 | **11,645** | 20.16.0; observability + LLM-judge |
| **Langfuse** (`langfuse/langfuse`) | MIT | **35,148** | 4.15.6 (2026-09-24); observability + LLM-judge; self-hostable |
| **Ragas** (`explodinggradients/ragas`) | Apache-2.0 | **15,868** | 0.4.3; RAG pipeline eval; **217 days inactive**; no tool-call assertions |
| replayproof (this repo, `agenteval`) | MIT | 0 (not launched) | 0.1.0, 2026-09-26 |

## The table

| | Licence | Offline replay, no keys | Tool-call contract assertions | Confidence bounds on pass rate | Cost regression gate | Reads other tools' transcripts |
|---|---|---|---|---|---|---|
| **EvalCore** | Apache-2.0 (Rust binary) | **Yes.** `--cache replay` "never falls through to a live request", needs no provider key, a cache miss fails the case | **Yes.** `trajectory` scorer on recorded traces: `must_call`, `must_not_call`, `before`/`after` ordering, `max_steps`, and `with:` arg matchers limited to `contains` / `equals` | **No.** `pass_rate` / `mean_score` are absolute floors; trials report pass fractions and flakiness, no interval bound | **No delta gate.** Cost and tokens are reported per case and run; `run.budget_usd` is an absolute per-run cap, and baselines store per-case pass/fail only ("no gate results or timing baked in") | **Yes, partly.** OTel / OpenInference exports and its own trajectory JSON. Not Inspect `.eval`, not message JSONL |
| **inspect_ai + inspect-replay** | MIT (both) | **Partial.** inspect-replay compares two recorded `.eval` logs offline and keyless; inspect_ai itself re-runs models and needs keys | **No.** Custom scorers can be written; inspect-replay diffs config fields, metrics and sample outcomes — it never looks at tool-call structure | **stderr, not a bound.** inspect_ai exposes `stderr()` and `bootstrap_stderr()` metrics on scores; no Wilson lower bound, and no default interval on a bare pass rate | **No.** Absolute token / turn limits exist in inspect_ai; there is no stored-baseline cost delta gate | **Inspect only.** inspect-replay reads `.eval` logs and nothing else; inspect_ai writes them |
| **inspect-mlflow** | MIT (Python, needs an MLflow tracking server) | **No replay story.** Hooks run against live Inspect evals; the comparison afterwards reads stored logs without calling a model | **No.** Tool calls are counted as telemetry (`total_tool_calls`); nothing asserts on sequence, arguments or forbidden tools | **Yes, for paired runs.** Comparison auto-selects McNemar's test for binary scores or a bootstrap CI for continuous ones, plus Cohen's d. Requires two aligned runs | **Reported, not gated.** Comparison computes `baseline_total_cost_usd` vs `candidate_total_cost_usd`, but there is no CLI command that exits non-zero on a cost delta | **Inspect only.** It is an entry-point hook for inspect_ai; the comparison reads Inspect logs |
| **DeepEval / promptfoo** | Apache-2.0 (DeepEval) · MIT (promptfoo) | **No.** Neither documents a record/replay cache. promptfoo caches provider responses (14-day TTL in `~/.promptfoo/cache`), and its own FAQ says strict offline use needs local providers or Enterprise on-prem. DeepEval: "Most of deepeval's metrics are LLM-as-a-Judge metrics and default to OpenAI" | **Yes — the strongest row against us.** promptfoo ships `tool-call-f1`, `is-valid-openai-tools-call`, and `trajectory:tool-used` / `tool-args-match` / `tool-sequence` / `step-count` (needs trace data). DeepEval ships `ToolCorrectnessMetric` and argument checks, LLM-judged (`usesLLMs`) | **Not found.** Neither docs set contains "confidence interval" or "wilson" for pass rates (searched 2026-09-26) | **Absolute only.** promptfoo's `cost` assertion checks cost is at or below a threshold; DeepEval has no cost gate (`token_cost` is a test-case field). Neither compares cost to a stored baseline | **promptfoo:** receives OTLP traces from your app or a tracing service. **DeepEval:** builds test cases from framework integrations. Neither reads Inspect `.eval` |
| **Braintrust** | SaaS / MIT SDK | **No.** Cloud-required by design: all results are posted to Braintrust servers; the SDK connects to `https://api.braintrust.dev`. A `BRAINTRUST_API_KEY` is required for every eval call. No local-only mode documented. | **No.** Scorer API checks output correctness (exact match, LLM rubric, similarity); no assertions over `required_tools`, `forbidden_tools`, `arg_schema`, or `no_pattern` | **No.** Experiments report a per-scorer average; no confidence interval or Wilson lower bound is surfaced | **No.** Platform UI shows cost history; no `braintrust gate --baseline` CLI command that exits non-zero on cost regression | **Braintrust datasets only.** The `Eval()` function runs against a dataset stored in Braintrust; it does not read existing JSONL transcripts. Data is uploaded to the platform. |
| **LangSmith** | SaaS / MIT SDK | **No.** `LANGCHAIN_API_KEY` required; results post to `smith.langchain.com`. Self-hosted option exists but requires infra. No keyless offline mode. | **No.** Evaluator API checks `run.outputs` dict — no assertions over tool-call sequences; tool calls appear in the trace view but are not an assertion target. `required_tools`, `forbidden_tools`, `arg_schema`, and `no_pattern` are absent from the SDK API | **No.** Evaluations report per-evaluator averages; no Wilson lower bound | **No.** Cost tracking exists in the platform UI; no CLI gate that exits non-zero on a token cost regression vs a committed baseline | **Tight LangChain coupling.** Full value requires LangChain decorators or `@traceable` wrapper on every tool; non-LangChain agents are supported but require wrapping all tool calls |
| **AgentOps** (AgentOps-AI) | MIT | **No.** Cloud-required by design: `agentops.init(api_key=...)` sends all session data to AgentOps servers. No offline mode documented. Stars: 5,847 (2026-09-28); last push 2026-06-25 | **No.** SDK records tool calls for cloud dashboard replay; no assertions on `required_tools`, `forbidden_tools`, `arg_schema`, or `no_pattern`. No YAML contract file. | **No.** Benchmark scores are point estimates in the cloud UI; no confidence interval. | **No.** Cost comparisons exist in the cloud UI; no CLI command that exits non-zero on a cost delta. | **AgentOps datasets only.** Session data is uploaded to AgentOps servers; there is no offline JSONL consumer. |
| **Arize Phoenix** (Arize-ai) | Apache-2.0 | **No documented offline mode.** `phoenix serve` starts a local server but evaluation runs with LLM-as-a-judge metrics require an API connection. Stars: 11,644 (2026-09-28); actively pushed 2026-09-28. | **No deterministic assertions.** `ToolEvaluator` assesses tool *relevance* via LLM judge (semantic match, not structural contract); `required_tools`, `forbidden_tools`, `arg_schema`, `no_pattern` are absent. | **No.** Experiment UI reports per-metric averages; no Wilson lower bound. | **No.** Cost tracked per experiment in the platform; no CLI gate that exits non-zero on a cost regression vs a committed baseline. | **OTel traces only.** Reads OpenTelemetry spans; does not read arbitrary JSONL transcripts. |
| **Langfuse** (langfuse) | MIT | **No documented offline mode.** Langfuse requires a running server (`langfuse serve` / Docker) and `LANGFUSE_SECRET_KEY`/`LANGFUSE_PUBLIC_KEY` on every SDK call. Stars: 35,141 (2026-09-28, **largest in the space**); actively pushed 2026-09-28. Self-hostable (MIT licence). | **No deterministic assertions.** Evaluation is via LLM-as-a-judge or human annotation; `required_tools`, `forbidden_tools`, `arg_schema`, `no_pattern` absent from README and docs. | **No.** Evaluations report per-metric averages; no Wilson lower bound. | **No.** Cost and token tracking in the platform UI; no CLI gate that exits non-zero on a cost regression vs a committed baseline. | **OTel / SDK traces only.** Reads traces captured via OpenTelemetry or the Langfuse SDK; does not read arbitrary JSONL transcripts. |
| **replayproof** | MIT (Python) | **Yes, by construction.** It never calls a model: recorded runs are the only input. README: "No API keys required. All tests run offline." | **Yes, deterministic and named.** 10 checks in a YAML contract: `tool_sequence`, `required_tools`, `forbidden_tools`, `arg_schema` (full JSON Schema validation of a tool's arguments), `max_tool_calls`, `max_tokens`, `max_latency_ms`, `no_pattern` (PII regex), `final_answer_matches`, `final_answer_not_empty` | **Yes, first-class.** 95% Wilson score lower bound in `SuiteResult`; the README demo reports 4/4 = 100% observed with a 51.0% lower bound | **Yes, delta against a stored baseline.** Any pass-rate drop, tokens +10%, cost +10%, or p95 latency +25% trips the gate and exits 1 (thresholds configurable) | **Own JSONL plus OpenAI/Anthropic-style message lists** via `record.from_messages()`. An Inspect `.eval` reader is named as a target in `docs/RESEARCH.md` but is **not implemented in v0.1** |

## Where this repo loses — read this first

- **EvalCore owns offline replay.** Content-addressed cassette, `--cache replay` with a
  hard fail on miss, no key, Rust binary, GitHub Action. That is the headline this repo
  originally wanted, already shipped and more mature. Do not claim replay innovation.
- **inspect-replay owns log diffing.** Sample alignment by stable id, a real ignorance
  taxonomy (`UNKNOWN` / `NOT_CHECKED` / `NOT_COMPARABLE` rather than a false green), and
  four distinct exit codes (0 no diff, 1 diff, 2 unreadable, 3 nothing alignable). It also
  documents its own assurance boundary. This repo has no sample-aligned two-log diff.
- **promptfoo has the broadest tool-call assertion surface** of anything in the table —
  trajectory assertions over OpenTelemetry traces plus `tool-call-f1` across OpenAI,
  Anthropic and Google tool-call shapes — and 25k stars of community behind it.
- **inspect-mlflow does real significance testing** (McNemar / bootstrap CI / Cohen's d).
  A Wilson lower bound is a confidence bound on one suite, not a paired test between two.
- **EvalCore's `trajectory` rules already cover required, forbidden, ordering and step
  budgets on recorded traces.** So "tool-call contract assertions" on their own is not a
  unique claim. The narrower, defensible difference: named YAML checks with JSON-Schema
  argument validation and PII patterns, a Wilson bound printed next to the pass rate, and
  a cost *delta* against a committed baseline — evaluated over a transcript that already
  exists, without re-running anything through a specific runner.
- **Braintrust and LangSmith have richer product ecosystems.** Braintrust offers dataset
  versioning, a prompt playground, and a managed experiment history UI. LangSmith has deep
  LangChain ecosystem integration and online production trace analysis. If managed SaaS
  with a rich UI is acceptable, either beats this repo on features.
- **AgentOps (5,847 stars) and Arize Phoenix (11,642 stars) are established in the
  monitoring and observability space.** AgentOps covers production monitoring, cost
  tracking, and session replay in a cloud dashboard. Phoenix covers LLM-as-a-judge
  evaluation, tracing, and experiment tracking. Both are far more mature as platforms.
  Neither competes on the contract+gate dimension, but they are the tools a team will
  reach for when "production observability" is the question. Acknowledge them in any
  conversation about the space.
- **v0.1 does not read Inspect `.eval` logs.** It reads its own JSONL and normalises
  OpenAI/Anthropic-style message lists. Say "planned", not "supported".

## Sources fetched for this file

- `eval-core/evalcore` README + evalcore.cc guides (record/replay, agents-and-traces,
  gates-and-baselines, trials-and-statistics, cost-and-budgets)
- `UKGovernmentBEIS/inspect_ai` repo, issue #1327 (open, created 2025-02-16), docs
  (`stderr`, `bootstrap_stderr`, token limits)
- `repowazdogz-droid/inspect-replay` README (exit codes, prior art, no PyPI)
- `debu-sinha/inspect-mlflow` README, `tests/test_comparison.py` (cost delta fields),
  PyPI release metadata
- `confident-ai/deepeval` docs (`metrics-tool-correctness.mdx`, FAQ), GitHub API
- `promptfoo/promptfoo` docs (`expected-outputs/deterministic.md`, `caching.md`,
  `tracing.md`, FAQ), GitHub API
- `braintrustdata/braintrust-sdk-python` README + PyPI description, GitHub API (c3-p02)
- `langchain-ai/langsmith-sdk` README + PyPI description, GitHub API (c3-p02)
- `AgentOps-AI/agentops` README, PyPI, GitHub API (c4-p02)
- `Arize-ai/phoenix` README, PyPI, GitHub API (c4-p02)
- `langfuse/langfuse` README (53,353 chars), PyPI, GitHub API (c5-p02)
- This repo: `README.md`, `CHANGELOG.md`, `src/agenteval/assertions.py`,
  `src/agenteval/budget.py`, `src/agenteval/record.py`

## Choose this when…

- **EvalCore** — choose it when you want to record once and replay the whole suite in CI,
  offline and keyless, with a cache miss failing the case. replayproof composes: export
  the trace, then assert the contract over it.
- **inspect_ai + inspect-replay** — choose them when you need the eval runner itself
  (retry, resume, logs) plus a rigorous, honest diff of two runs. Choose replayproof when
  the question is "which contract broke", not "which sample moved".
- **inspect-mlflow** — choose it when you have two aligned runs and need to know whether
  the change is statistically meaningful, and you already run an MLflow server.
- **DeepEval / promptfoo** — choose promptfoo for breadth of providers, assertions and
  red-teaming, and DeepEval for an LLM-judged metric library inside pytest. Choose
  replayproof when the question is structural, deterministic, and must cost zero keys.
- **Braintrust** — choose it when your team wants a SaaS platform with dataset versioning,
  a prompt playground, and experiment history UI, and cloud data residency is acceptable.
- **LangSmith** — choose it when your stack is LangChain/LangGraph and you want production
  trace analysis integrated with your eval history in a managed platform.
- **AgentOps** — choose it when you want production monitoring, cost tracking, and session
  replay in a cloud dashboard with framework integrations out of the box.
- **Arize Phoenix** — choose it when you want LLM-as-a-judge evaluation, OTel-native
  tracing, and a self-hosted or managed experiment tracking UI.
- **Langfuse** — choose it when you want the largest open-source observability platform
  (35,141 stars) with self-hosting via Docker, OTel-native tracing, LLM-as-a-judge evals,
  and a team-facing dashboard. It is the MIT-licenced self-hostable alternative to
  Braintrust and LangSmith.
- **replayproof** — choose it when recordings already exist, the gate must be
  deterministic, data must not leave the machine, and one command has to fail the build
  on a broken tool contract, a Wilson-uncertain pass rate, or a token-cost regression.

## How it composes with Inspect

Inspect runs the eval and writes the `.eval` log; inspect-replay tells you which samples
changed and refuses to pretend it can compare what it cannot; replayproof sits on top of
the same recordings and tells you which tool-call contract broke, with a 95% Wilson bound,
and exits non-zero when token cost regressed against your stored baseline.

