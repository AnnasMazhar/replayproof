"""Recording proxy that wraps a callable agent and captures every tool call.

The Recorder accepts a deterministic clock callable so tests are not
dependent on wall time.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from agenteval.transcript import SCHEMA_VERSION, Run, ToolCall, Turn


class Recorder:
    """Wraps an agent callable and records its tool calls into a Run.

    Args:
        agent: Callable ``(task: str, tools: dict) -> str`` that produces a
               final answer string.
        agent_id: Identifier stored on the resulting Run.
        model: Model name stored on the resulting Run.
        provider: Provider name stored on the resulting Run.
        clock: Callable returning monotonic seconds; defaults to
               ``time.monotonic``.  Injected for deterministic testing.
        started_at: ISO-8601 timestamp for the Run; if not provided, an
                    empty string is used (caller should inject for stability).
    """

    def __init__(
        self,
        agent: Callable[[str, dict[str, Callable[..., Any]]], str],
        agent_id: str = "unnamed",
        model: str = "",
        provider: str = "",
        clock: Callable[[], float] | None = None,
        started_at: str = "",
    ) -> None:
        self._agent = agent
        self._agent_id = agent_id
        self._model = model
        self._provider = provider
        self._clock = clock if clock is not None else time.monotonic
        self._started_at = started_at

    def record(self, task: str, tools: dict[str, Callable[..., Any]]) -> Run:
        """Run the agent on *task* and return a fully-populated Run.

        Each tool in *tools* is instrumented to capture args, result, error,
        and duration.  The agent sees the instrumented wrappers transparently.

        Args:
            task: The prompt / task string passed to the agent.
            tools: Mapping of tool name to callable.

        Returns:
            A complete Run with all turns and tool calls recorded.
        """
        recorded_calls: list[ToolCall] = []

        def make_wrapper(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapper(**kwargs: Any) -> Any:
                t0 = self._clock()
                error: str | None = None
                result: Any = None
                try:
                    result = fn(**kwargs)
                except Exception as exc:
                    error = str(exc)
                    raise
                finally:
                    duration_ms = (self._clock() - t0) * 1000.0
                    recorded_calls.append(
                        ToolCall(
                            name=name,
                            args=dict(kwargs),
                            result=result,
                            error=error,
                            duration_ms=duration_ms,
                        )
                    )
                return result

            return wrapper

        instrumented = {name: make_wrapper(name, fn) for name, fn in tools.items()}

        t_start = self._clock()
        final_answer = self._agent(task, instrumented)
        total_ms = (self._clock() - t_start) * 1000.0

        turns = (
            Turn(role="user", content=task),
            Turn(
                role="assistant",
                content=final_answer,
                tool_calls=tuple(recorded_calls),
                latency_ms=total_ms,
            ),
        )

        return Run(
            name=task[:64],
            agent_id=self._agent_id,
            model=self._model,
            provider=self._provider,
            started_at=self._started_at,
            turns=turns,
            total_tokens_in=0,
            total_tokens_out=0,
            total_latency_ms=total_ms,
            schema_version=SCHEMA_VERSION,
        )


def from_messages(messages: list[dict[str, Any]], **kwargs: Any) -> Run:
    """Normalise an OpenAI/Anthropic-style message list into a Run.

    Args:
        messages: List of message dicts with at least ``role`` and ``content``
                  keys.  Tool calls may appear as ``tool_calls`` on assistant
                  messages.
        **kwargs: Passed directly to ``Run.__init__`` (name, agent_id, model,
                  provider, started_at are honoured).

    Returns:
        A Run assembled from the provided message list.
    """
    from agenteval.transcript import SCHEMA_VERSION, Run, ToolCall, Turn

    turns: list[Turn] = []
    total_tokens_in = 0
    total_tokens_out = 0
    total_latency_ms = 0.0

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "") or ""
        tokens_in = int(msg.get("tokens_in", 0))
        tokens_out = int(msg.get("tokens_out", 0))
        latency_ms = float(msg.get("latency_ms", 0.0))

        raw_calls = msg.get("tool_calls") or []
        tool_calls: list[ToolCall] = []
        for tc in raw_calls:
            # Support both agenteval and OpenAI-style shapes.
            if "name" in tc:
                tool_calls.append(ToolCall.from_dict(tc))
            elif "function" in tc:
                fn = tc["function"]
                import json as _json

                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    args = _json.loads(args)
                tool_calls.append(ToolCall(name=fn.get("name", ""), args=args))

        total_tokens_in += tokens_in
        total_tokens_out += tokens_out
        total_latency_ms += latency_ms

        turns.append(
            Turn(
                role=role,
                content=content,
                tool_calls=tuple(tool_calls),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
        )

    return Run(
        name=kwargs.get("name", ""),
        agent_id=kwargs.get("agent_id", ""),
        model=kwargs.get("model", ""),
        provider=kwargs.get("provider", ""),
        started_at=kwargs.get("started_at", ""),
        turns=tuple(turns),
        total_tokens_in=total_tokens_in,
        total_tokens_out=total_tokens_out,
        total_latency_ms=total_latency_ms,
        schema_version=SCHEMA_VERSION,
    )
