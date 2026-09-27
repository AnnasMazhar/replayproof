#!/usr/bin/env python3
"""Record REAL agent runs (real models, real tool calls) into the replayproof schema.

Why a separate script and not ``agenteval record``: ``agenteval record`` records a
deterministic in-process Python agent and cannot carry per-turn token accounting
from a live provider. This script drives a real model (local Ollama or a hosted
OpenAI-compatible API), runs a real tool loop, and writes one ``Run`` per line in
the exact ``agenteval.transcript.Run`` JSONL schema, with provider-reported token
counts.

Tool-call protocol: ``json-envelope-v1``.
    Ollama refuses native tool schemas for gemma3:4b (HTTP 400 ``registry.ollama.ai/
    library/gemma3:4b does not support tools``), so both providers use the same
    prompting-based envelope so that the SAME prompt is sent to every model:

        {"tool": "search_docs", "args": {"query": "..."}}

    The scaffold parses that envelope, executes the tool, and feeds the result
    back as a ``role=tool`` message. The model decides whether to call, which
    tool, and with what arguments; the scaffold only routes.

Redaction: every string field is passed through ``redact()`` before serialisation
so host paths / internal system names never reach the committed file.

Usage (see docs/EVIDENCE.md for the exact commands used for each recording):

    python scripts/record_real_run.py \
        --provider ollama --model gemma3:4b --prompt-mode full \
        --out examples/recordings/real_gemma3_4b_full.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# --------------------------------------------------------------------------- #
# Fixed task set — identical across every recording so drift aligns case-by-case
# --------------------------------------------------------------------------- #

TASKS: list[dict[str, str]] = [
    {
        "case_id": "case-01",
        "task": "How much power does a typical residential solar system produce?",
    },
    {
        "case_id": "case-02",
        "task": "What battery chemistry is most common in home storage systems?",
    },
    {
        "case_id": "case-03",
        "task": "How many days does solar panel installation take?",
    },
    {
        "case_id": "case-04",
        "task": "What roof factors affect the energy production of a rooftop array?",
    },
    {
        "case_id": "case-05",
        "task": "Are lead-acid batteries more efficient than lithium-ion batteries?",
    },
    {
        "case_id": "case-06",
        "task": "How are most new solar systems connected to the grid?",
    },
]

FULL_SYSTEM = (
    "You are a research assistant. You answer strictly from the document corpus, "
    "using the search_docs tool to look things up.\n"
    "To call a tool, reply with EXACTLY one JSON object and nothing else:\n"
    '{"tool": "search_docs", "args": {"query": "<search terms>"}}\n'
    "After a TOOL result is returned you may search again or give the final answer. "
    "When you have enough information, reply with a plain-text final answer "
    "(no JSON, no tool call)."
)

NARROWED_SYSTEM = (
    "You are a terse assistant. Answer the question directly from your own "
    "knowledge in one short sentence. Do not use any tools."
)

TOOL_SPECS = [{"name": "search_docs", "args": {"query": "<search terms>"}}]

MAX_STEPS = 8

# --------------------------------------------------------------------------- #
# Redaction — CI enforces: no host paths, no internal system names
# --------------------------------------------------------------------------- #

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"/home/[A-Za-z0-9._-]+"), "[HOME]"),
    (re.compile(r"(?<![A-Za-z])openclaw(?![A-Za-z])"), "[USER]"),
]


def redact(text: str) -> str:
    """Replace internal host paths / system names with placeholders."""
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


# --------------------------------------------------------------------------- #
# Providers — both hit OpenAI-compatible /chat/completions
# --------------------------------------------------------------------------- #


def _load_env_file() -> dict[str, str]:
    """Read KEY=VALUE pairs from ~/.hermes/.env without ever printing them."""
    env: dict[str, str] = {}
    path = os.path.expanduser("~/.hermes/.env")
    if not os.path.exists(path):
        return env
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


# Cloudflare (error 1010) blocks urllib's default User-Agent on api.groq.com.
_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class ProviderError(RuntimeError):
    """Raised when a provider rejects a request (recorded verbatim by callers)."""


_REJECTED_REQUESTS = 0


def _failed_generation(detail: str) -> str | None:
    """Extract ``error.failed_generation`` from a provider error body, if present."""
    try:
        body = json.loads(detail)
    except (json.JSONDecodeError, ValueError):
        return None
    failed = (body.get("error") or {}).get("failed_generation")
    if isinstance(failed, str) and failed.strip():
        return failed
    return None


def chat_completion(
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
) -> tuple[str, int, int, float]:
    """Call the provider; return (content, tokens_in, tokens_out, latency_ms)."""
    if provider == "ollama":
        url = "http://localhost:11434/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        key = ""
    elif provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        key = _load_env_file().get("GROQ_API_KEY", "")
        if not key:
            raise ProviderError("GROQ_API_KEY not found in environment or ~/.hermes/.env")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": _BROWSER_UA,
        }
    else:
        raise ProviderError(f"unknown provider: {provider!r}")

    payload = json.dumps(
        {"model": model, "messages": messages, "temperature": temperature}
    ).encode()

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:2000]
        # Groq's gateway rejects a generation that looks like a native tool call
        # ({"name": ..., "arguments": ...}) when the request carried no tools:
        # HTTP 400 "Tool choice is none, but model called a tool". The model's
        # REAL generation comes back in error.failed_generation — surface it
        # instead of losing the turn. The provider reports no usage for a
        # rejected request, so tokens for that step are recorded as 0 and the
        # rejection is counted in run metadata.
        failed = _failed_generation(detail)
        if failed is not None:
            global _REJECTED_REQUESTS
            _REJECTED_REQUESTS += 1
            print(
                "[debug] provider rejected native tool-call shape; "
                "recovered failed_generation as content",
                file=sys.stderr,
            )
            return failed, 0, 0, (time.perf_counter() - started) * 1000.0
        raise ProviderError(f"HTTP {exc.code} from {provider}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"cannot reach {provider}: {exc.reason}") from exc
    latency_ms = (time.perf_counter() - started) * 1000.0

    choice = body["choices"][0]
    message = choice["message"]
    content = message.get("content") or ""
    if not content.strip():
        # Reasoning models sometimes emit only the `reasoning` field.
        # Keep the raw response for diagnosis; never fabricate a tool envelope.
        dump = f"/tmp/opencode/empty_content_{int(time.time())}_{model.replace('/', '_')}.json"
        try:
            with open(dump, "w", encoding="utf-8") as fh:
                json.dump(body, fh, indent=2)
            print(f"[debug] empty content; raw response saved to {dump}", file=sys.stderr)
        except OSError:
            pass
        content = message.get("reasoning") or ""
        content = f"[no-content finish_reason={choice.get('finish_reason')}] {content}"
    usage = body.get("usage") or {}
    tokens_in = int(usage.get("prompt_tokens", 0))
    tokens_out = int(usage.get("completion_tokens", 0))
    return content, tokens_in, tokens_out, latency_ms


# --------------------------------------------------------------------------- #
# json-envelope-v1 tool protocol
# --------------------------------------------------------------------------- #


def parse_envelope(content: str) -> dict[str, Any] | None:
    """Return {'tool':..., 'args':...} if the model emitted a tool envelope."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    # raw_decode tolerates trailing junk (gemma3:4b sometimes emits an extra
    # closing brace or a period after the envelope) that json.loads rejects.
    decoder = json.JSONDecoder()
    candidates = [text]
    first = text.find("{")
    if first >= 0:
        candidates.append(text[first:])
    for cand in candidates:
        try:
            obj, _end = decoder.raw_decode(cand.lstrip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and ("tool" in obj or "name" in obj):
            name = obj.get("tool") or obj.get("name")
            args = obj.get("args") or obj.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    args = {"_raw": args}
            if isinstance(name, str) and isinstance(args, dict):
                return {"tool": name, "args": args}
    return None


def build_tools() -> dict[str, Any]:
    """Tool set: keyword search over the same fixture corpus the demo agent uses.

    The demo agent's exact-substring search returns nothing for natural-language
    queries (e.g. "battery chemistry home storage"), so this variant scores
    sentences by keyword overlap (>=4-char tokens, prefix-matched to tolerate
    plurals) and returns the top hits. Deterministic for a given query.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from examples.research_agent import FIXTURE_DOCS  # noqa: E402

    def search_docs(query: str) -> str:
        tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 4]
        scored: list[tuple[int, str, str]] = []
        for doc_name in sorted(FIXTURE_DOCS):
            for sentence in FIXTURE_DOCS[doc_name].split("."):
                sentence = sentence.strip()
                if not sentence:
                    continue
                words = re.findall(r"[a-z0-9]+", sentence.lower())
                score = sum(
                    1
                    for tok in tokens
                    if tok in sentence.lower() or any(w.startswith(tok[:5]) for w in words)
                )
                if score:
                    scored.append((score, doc_name, sentence))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        if not scored:
            return json.dumps({"results": [], "message": "No results found."})
        results = [{"doc": d, "snippet": s} for _score, d, s in scored[:3]]
        return json.dumps({"results": results})

    return {"search_docs": search_docs}


# --------------------------------------------------------------------------- #
# One case = one Run
# --------------------------------------------------------------------------- #


def run_case(
    provider: str,
    model: str,
    case_id: str,
    task: str,
    system: str,
    tools: dict[str, Any],
    prompt_mode: str,
    advertise_tools: bool,
) -> dict[str, Any]:
    """Drive the model through the tool loop and build one Run dict."""
    from agenteval.transcript import Run, ToolCall, Turn

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]
    turns: list[Turn] = [
        Turn(role="system", content=system),
        Turn(role="user", content=task),
    ]
    total_in = total_out = 0
    total_latency = 0.0
    final_content = ""
    used_tools: list[str] = []
    rejected_before = _REJECTED_REQUESTS

    for _step in range(MAX_STEPS):
        content, t_in, t_out, latency_ms = chat_completion(provider, model, messages)
        total_in += t_in
        total_out += t_out
        total_latency += latency_ms
        messages.append({"role": "assistant", "content": content})

        envelope = parse_envelope(content) if advertise_tools else None
        if envelope is None:
            final_content = content
            turns.append(
                Turn(
                    role="assistant",
                    content=content,
                    tokens_in=t_in,
                    tokens_out=t_out,
                    latency_ms=latency_ms,
                )
            )
            break

        tool_name = envelope["tool"]
        args = envelope["args"]
        fn = tools.get(tool_name)
        t0 = time.perf_counter()
        error: str | None = None
        if fn is None:
            result = json.dumps({"error": f"unknown tool: {tool_name}"})
            error = f"unknown tool: {tool_name}"
        else:
            try:
                result = str(fn(**args))
            except Exception as exc:  # noqa: BLE001 — real tools raise real errors
                result = json.dumps({"error": str(exc)})
                error = str(exc)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        used_tools.append(tool_name)

        turns.append(
            Turn(
                role="assistant",
                content=content,
                tool_calls=(
                    ToolCall(
                        name=tool_name,
                        args=args,
                        result=_json_loads(result),
                        error=error,
                        duration_ms=duration_ms,
                    ),
                ),
                tokens_in=t_in,
                tokens_out=t_out,
                latency_ms=latency_ms,
            )
        )
        turns.append(Turn(role="tool", content=result))
        # Delivered as a *user* message: gemma3:4b has no native tool template,
        # and a wire-level role="tool" turn makes it answer with EOS/refusals.
        messages.append({"role": "user", "content": f"TOOL RESULT for {tool_name}:\n{result}"})
    else:
        final_content = "(max steps reached without a final answer)"
        turns.append(Turn(role="assistant", content=final_content))

    run = Run(
        name=case_id,
        agent_id=f"record_real_run:{provider}:{model}",
        model=model,
        provider=provider,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        turns=tuple(turns),
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_latency_ms=total_latency,
        metadata={
            "protocol": "json-envelope-v1",
            "tool_result_delivery": "user-message",
            "prompt_mode": prompt_mode,
            "tools_advertised": advertise_tools,
            "temperature": 0.0,
            "provider_rejected_requests": _REJECTED_REQUESTS - rejected_before,
            "task": task,
            "tools_used": used_tools,
        },
    )
    return _redact_value(run.to_dict())


def _json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["ollama", "groq"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt-mode", choices=["full", "narrowed"], default="full")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--cases",
        default="",
        help="Optional comma-separated case ids to record (default: all)",
    )
    args = parser.parse_args()

    if args.prompt_mode == "full":
        system = FULL_SYSTEM
        advertise_tools = True
    else:
        system = NARROWED_SYSTEM
        advertise_tools = True  # tools stay available; only the prompt is narrowed

    tools = build_tools()
    wanted = {c.strip() for c in args.cases.split(",") if c.strip()}
    tasks = [t for t in TASKS if not wanted or t["case_id"] in wanted]
    if not tasks:
        print(f"error: no cases match {args.cases!r}", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for spec in tasks:
            run = run_case(
                provider=args.provider,
                model=args.model,
                case_id=spec["case_id"],
                task=spec["task"],
                system=system,
                tools=tools,
                prompt_mode=args.prompt_mode,
                advertise_tools=advertise_tools,
            )
            fh.write(json.dumps(run, sort_keys=True, separators=(",", ":")) + "\n")
            fh.flush()
            used = run["metadata"]["tools_used"]
            print(
                f"{spec['case_id']} {args.provider}:{args.model} "
                f"tokens={run['total_tokens_in']}/{run['total_tokens_out']} "
                f"tools={used or 'none'} final={run['turns'][-1]['content'][:70]!r}"
            )
    print(f"wrote {len(tasks)} runs -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
