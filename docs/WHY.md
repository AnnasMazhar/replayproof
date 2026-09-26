# Why

Offline replay with zero API keys already exists elsewhere. EvalCore's `--cache replay`
is offline, keyless, and fails the case on a cache miss instead of silently calling live.
inspect-replay already diffs two Inspect logs sample by sample and reports
`NOT_COMPARABLE` rather than a false green. Both are more mature at those jobs than this
repository would be if it tried to compete.

So this is not an eval framework. It does not run models, keep a database of runs, or
grade answers with a judge. It reads runs other tools already recorded and asks the three
questions those tools leave open: which tool-call contract broke — required, forbidden,
ordered, argument schema, PII pattern, call budget; what the pass rate is with a 95%
Wilson lower bound instead of a bare percentage; and whether tokens, cost, or p95 latency
regressed against a stored baseline. The gate exits non-zero and the build stops.

It composes with Inspect, which keeps running, logging, retrying and resuming exactly as
before; with EvalCore, which owns the cassette replay; and with anything that emits
OpenAI/Anthropic-style message lists or JSONL, which is what most frameworks already
write to disk. Use the eval framework for the score. Use this for the contract, the
confidence bound, and the cost gate.
