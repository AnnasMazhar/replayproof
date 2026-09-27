"""Offline replay of recorded agent runs.

Replay modes:
    strict  — every tool call must exist in the provided tools dict and
              return exactly the recorded result; raises ReplayMismatch on
              any deviation.
    lenient — unknown tools return None; mismatches are recorded as warnings
              on the new Run's metadata.
    dry     — no tool is executed; results are copied from the recording.
              A dry replay serialises byte-identically to the original Run
              (acceptance test).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from agenteval.transcript import Run, ToolCall, Turn


class ReplayMismatch(Exception):  # noqa: N818
    """Raised when a strict-mode replay encounters a result mismatch.

    Attributes:
        tool_name: Name of the offending tool call.
        expected: The result captured in the original recording.
        actual: The result returned by the tool during replay.
    """

    def __init__(self, tool_name: str, expected: Any, actual: Any) -> None:
        self.tool_name = tool_name
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"ReplayMismatch on tool '{tool_name}': " f"expected={expected!r}, actual={actual!r}"
        )


def replay(
    run: Run,
    tools: dict[str, Callable[..., Any]],
    *,
    mode: Literal["strict", "lenient", "dry"] = "dry",
) -> Run:
    """Replay a recorded Run, optionally executing real tools.

    Args:
        run: The original recorded Run to replay.
        tools: Mapping of tool name to callable.  Only consulted in strict
               and lenient modes.
        mode: One of 'strict', 'lenient', 'dry'.  See module docstring.

    Returns:
        A new Run that mirrors the original structure.  In dry mode the
        result is byte-identical to the original when both are serialised
        with ``Run.to_jsonl()``.

    Raises:
        ReplayMismatch: In strict mode, if any tool result diverges from
                        the recording.
    """
    warnings: list[str] = []
    new_turns: list[Turn] = []

    for turn in run.turns:
        new_calls: list[ToolCall] = []
        for tc in turn.tool_calls:
            if mode == "dry":
                new_calls.append(tc)
            elif mode == "strict":
                fn = tools.get(tc.name)
                if fn is None:
                    raise ReplayMismatch(
                        tc.name,
                        expected=tc.result,
                        actual="<tool not found>",
                    )
                actual = fn(**tc.args)
                if actual != tc.result:
                    raise ReplayMismatch(tc.name, expected=tc.result, actual=actual)
                new_calls.append(
                    ToolCall(
                        name=tc.name,
                        args=tc.args,
                        result=actual,
                        error=tc.error,
                        duration_ms=tc.duration_ms,
                    )
                )
            elif mode == "lenient":
                fn = tools.get(tc.name)
                if fn is None:
                    warnings.append(f"lenient: tool '{tc.name}' not found; using recorded result")
                    new_calls.append(tc)
                else:
                    actual = fn(**tc.args)
                    if actual != tc.result:
                        warnings.append(
                            f"lenient: tool '{tc.name}' result mismatch "
                            f"(expected={tc.result!r}, actual={actual!r})"
                        )
                    new_calls.append(
                        ToolCall(
                            name=tc.name,
                            args=tc.args,
                            result=actual,
                            error=tc.error,
                            duration_ms=tc.duration_ms,
                        )
                    )
            else:
                raise ValueError(f"Unknown replay mode: {mode!r}")

        new_turns.append(
            Turn(
                role=turn.role,
                content=turn.content,
                tool_calls=tuple(new_calls),
                tokens_in=turn.tokens_in,
                tokens_out=turn.tokens_out,
                latency_ms=turn.latency_ms,
            )
        )

    new_metadata = dict(run.metadata)
    if warnings:
        new_metadata["replay_warnings"] = warnings

    return Run(
        name=run.name,
        agent_id=run.agent_id,
        model=run.model,
        provider=run.provider,
        started_at=run.started_at,
        turns=tuple(new_turns),
        total_tokens_in=run.total_tokens_in,
        total_tokens_out=run.total_tokens_out,
        total_latency_ms=run.total_latency_ms,
        metadata=new_metadata,
        schema_version=run.schema_version,
    )
