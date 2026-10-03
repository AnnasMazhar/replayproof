"""Data model for agent evaluation transcripts.

All dataclasses are frozen (immutable) and JSON-serialisable.
Schema version is embedded in every Run so forward-compatible loading is possible.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation within a turn.

    Fields:
        name: The tool function name.
        args: Arguments passed to the tool (must be JSON-serialisable).
        result: The value returned by the tool, or None if an error occurred.
        error: Error message string if the call failed, else None.
        duration_ms: Wall-clock duration of the tool execution in milliseconds.
    """

    name: str
    args: dict[str, Any]
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolCall:
        """Construct from a dict; unknown keys are silently dropped."""
        return cls(
            name=d["name"],
            args=d.get("args", {}),
            result=d.get("result"),
            error=d.get("error"),
            duration_ms=float(d.get("duration_ms", 0.0)),
        )


@dataclass(frozen=True)
class Turn:
    """One conversational turn (system/user/assistant/tool).

    Fields:
        role: One of 'system', 'user', 'assistant', 'tool'.
        content: Text content of the turn.
        tool_calls: Tool invocations that occurred during this turn.
        tokens_in: Prompt tokens consumed.
        tokens_out: Completion tokens produced.
        latency_ms: Latency from send to first token in milliseconds.
    """

    role: str
    content: str
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Turn:
        """Construct from a dict; unknown keys are silently dropped."""
        return cls(
            role=d["role"],
            content=d.get("content", ""),
            tool_calls=tuple(ToolCall.from_dict(tc) for tc in d.get("tool_calls", [])),
            tokens_in=int(d.get("tokens_in", 0)),
            tokens_out=int(d.get("tokens_out", 0)),
            latency_ms=float(d.get("latency_ms", 0.0)),
        )


@dataclass(frozen=True)
class Run:
    """A complete agent run: all turns, totals, and identifying metadata.

    Fields:
        name: Human-readable name for this run (e.g. test case id).
        agent_id: Identifier for the agent under test.
        model: Model name (e.g. 'gpt-4o', 'claude-3-5-sonnet').
        provider: Provider name (e.g. 'openai', 'anthropic').
        started_at: ISO-8601 timestamp of run start (injected by recorder).
        turns: Ordered sequence of conversation turns.
        total_tokens_in: Sum of tokens_in across all turns.
        total_tokens_out: Sum of tokens_out across all turns.
        total_latency_ms: Sum of latency_ms across all turns.
        metadata: Catch-all dict for extra fields (forward-compatibility).
        schema_version: Version of this schema; always "1" for v0.1.
    """

    name: str
    agent_id: str
    model: str
    provider: str
    started_at: str
    turns: tuple[Turn, ...]
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def all_tool_calls(self) -> list[ToolCall]:
        """Return all tool calls across all turns in order."""
        result: list[ToolCall] = []
        for turn in self.turns:
            result.extend(turn.tool_calls)
        return result

    def final_content(self) -> str:
        """Return the content of the last assistant turn, or empty string."""
        for turn in reversed(self.turns):
            if turn.role == "assistant":
                return turn.content
        return ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "agent_id": self.agent_id,
            "model": self.model,
            "provider": self.provider,
            "started_at": self.started_at,
            "turns": [t.to_dict() for t in self.turns],
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_latency_ms": self.total_latency_ms,
            "metadata": self.metadata,
        }

    def to_jsonl(self) -> str:
        """Serialise to a single JSONL line (no trailing newline)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Run:
        """Construct from a dict.

        Unknown top-level keys are preserved in metadata for forward compatibility.
        Missing optional fields are defaulted.
        """
        known_keys = {
            "schema_version",
            "name",
            "agent_id",
            "model",
            "provider",
            "started_at",
            "turns",
            "total_tokens_in",
            "total_tokens_out",
            "total_latency_ms",
            "metadata",
        }
        extra = {k: v for k, v in d.items() if k not in known_keys}
        # metadata may be absent or explicitly null in a forward-compatible recording;
        # default to an empty dict in both cases.
        raw_meta = d.get("metadata") or {}
        base_metadata = dict(raw_meta)
        base_metadata.update(extra)

        return cls(
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            name=d["name"],
            agent_id=d.get("agent_id", ""),
            model=d.get("model", ""),
            provider=d.get("provider", ""),
            started_at=d.get("started_at", ""),
            turns=tuple(Turn.from_dict(t) for t in d.get("turns", [])),
            total_tokens_in=int(d.get("total_tokens_in", 0)),
            total_tokens_out=int(d.get("total_tokens_out", 0)),
            total_latency_ms=float(d.get("total_latency_ms", 0.0)),
            metadata=base_metadata,
        )

    @classmethod
    def from_jsonl(cls, line: str) -> Run:
        """Deserialise from a single JSONL line."""
        return cls.from_dict(json.loads(line))
