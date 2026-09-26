"""Tests for replay determinism and ReplayMismatch behaviour.

Faults detected by each test:

- test_dry_replay_byte_identical: catches any replay.replay(mode='dry') implementation
  that mutates any field of the Run (e.g. resets started_at, changes turn order,
  or loses metadata). The test serialises both original and replayed Run and compares
  byte-for-byte.
  Fault injection: change replay() to rebuild started_at as empty string
  => JSON differs => test fails.

- test_strict_mode_raises_on_mismatch: catches a strict-mode replay that swallows
  tool result mismatches instead of raising ReplayMismatch.
  Fault injection: remove the `if actual != tc.result: raise ReplayMismatch(...)` guard
  => no exception raised => test fails.

- test_replay_mismatch_carries_expected_actual: catches a ReplayMismatch that is raised
  with None/empty expected/actual fields, making the diff useless.
  Fault injection: raise ReplayMismatch(name, None, None) => assertion on .expected fails.

- test_strict_mode_raises_on_missing_tool: catches strict replay that silently ignores
  a missing tool instead of raising.
  Fault injection: return None for missing tool instead of raising => test fails.

- test_lenient_mode_records_warning: catches lenient replay that discards mismatch
  warnings instead of recording them on the new Run's metadata.
  Fault injection: remove the `warnings.append(...)` call => no warnings key => test fails.

- test_lenient_mode_unknown_tool_uses_recorded_result: catches lenient replay that crashes
  on an unknown tool instead of falling back to the recorded result.
  Fault injection: raise KeyError for missing tool in lenient mode => test fails.

- test_dry_mode_no_tools_needed: catches dry replay that fails when tools dict is empty
  (dry mode must not consult tools at all).
  Fault injection: look up tools[tc.name] in dry mode => KeyError => test fails.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from agenteval.replay import ReplayMismatch, replay
from agenteval.transcript import Run, ToolCall, Turn


def _make_run_with_tool_calls(
    name: str = "test_run",
    tool_results: dict | None = None,
) -> Run:
    """Build a minimal Run with two tool calls for testing."""
    if tool_results is None:
        tool_results = {"search": "result_A", "summarise": "summary_X"}

    tool_calls = tuple(
        ToolCall(name=tname, args={"q": "test"}, result=tresult)
        for tname, tresult in sorted(tool_results.items())
    )

    return Run(
        name=name,
        agent_id="test_agent",
        model="none",
        provider="local",
        started_at="2026-01-01T00:00:00Z",
        turns=(
            Turn(role="user", content="hello"),
            Turn(
                role="assistant",
                content="done",
                tool_calls=tool_calls,
                latency_ms=50.0,
            ),
        ),
        total_tokens_in=10,
        total_tokens_out=5,
        total_latency_ms=50.0,
        metadata={"extra": "preserved"},
    )


class TestDryReplay:
    """Fault detected: dry replay mutates any field of the Run."""

    def test_dry_replay_byte_identical(self) -> None:
        """Dry replay must reproduce the original Run byte-identically when serialised."""
        original = _make_run_with_tool_calls()
        replayed = replay(original, tools={}, mode="dry")

        assert original.to_jsonl() == replayed.to_jsonl(), (
            "Dry replay serialisation differs from original. "
            "Check that no fields are modified in dry mode."
        )

    def test_dry_mode_no_tools_needed(self) -> None:
        """Dry mode must not consult the tools dict at all (even if empty)."""
        original = _make_run_with_tool_calls()
        # Empty tools dict: would crash if dry mode tried to look up a tool.
        replayed = replay(original, tools={}, mode="dry")
        assert len(replayed.all_tool_calls()) == len(original.all_tool_calls())


class TestStrictReplay:
    """Fault detected: strict replay swallows mismatches."""

    def test_strict_mode_raises_on_mismatch(self) -> None:
        """Strict mode must raise ReplayMismatch when tool returns different result."""
        original = _make_run_with_tool_calls(tool_results={"search": "correct_result"})

        # Tool returns a different result than recorded.
        tools = {"search": lambda q: "WRONG_RESULT"}

        with pytest.raises(ReplayMismatch) as exc_info:
            replay(original, tools=tools, mode="strict")

        err = exc_info.value
        assert err.tool_name == "search", f"Expected tool_name='search', got {err.tool_name!r}"

    def test_replay_mismatch_carries_expected_actual(self) -> None:
        """ReplayMismatch must carry both expected and actual values for the diff."""
        original = _make_run_with_tool_calls(tool_results={"search": "expected_value"})
        tools = {"search": lambda q: "actual_value"}

        with pytest.raises(ReplayMismatch) as exc_info:
            replay(original, tools=tools, mode="strict")

        err = exc_info.value
        assert (
            err.expected == "expected_value"
        ), f"ReplayMismatch.expected should be 'expected_value', got {err.expected!r}"
        assert (
            err.actual == "actual_value"
        ), f"ReplayMismatch.actual should be 'actual_value', got {err.actual!r}"

    def test_strict_mode_raises_on_missing_tool(self) -> None:
        """Strict mode must raise ReplayMismatch when a recorded tool is absent."""
        original = _make_run_with_tool_calls(tool_results={"search": "result"})
        # Empty tools — 'search' is not registered.
        with pytest.raises(ReplayMismatch):
            replay(original, tools={}, mode="strict")

    def test_strict_mode_passes_on_matching_result(self) -> None:
        """Strict mode must not raise when the tool returns the recorded result."""
        original = _make_run_with_tool_calls(
            tool_results={"search": "correct_result", "summarise": "summary_X"}
        )
        tools = {
            "search": lambda q: "correct_result",
            "summarise": lambda q: "summary_X",
        }
        replayed = replay(original, tools=tools, mode="strict")
        assert len(replayed.all_tool_calls()) == 2


class TestLenientReplay:
    """Fault detected: lenient replay crashes or drops warnings."""

    def test_lenient_mode_records_warning_on_mismatch(self) -> None:
        """Lenient mode must record a warning when a tool result mismatches."""
        original = _make_run_with_tool_calls(tool_results={"search": "expected"})
        tools = {"search": lambda q: "different"}
        replayed = replay(original, tools=tools, mode="lenient")
        warnings = replayed.metadata.get("replay_warnings", [])
        assert len(warnings) > 0, "Lenient replay must record a warning when a mismatch occurs."
        assert any(
            "mismatch" in w.lower() for w in warnings
        ), f"Warning should mention 'mismatch'. Got: {warnings}"

    def test_lenient_mode_unknown_tool_uses_recorded_result(self) -> None:
        """Lenient mode must fall back to the recorded result for unknown tools."""
        original = _make_run_with_tool_calls(tool_results={"search": "recorded_result"})
        # 'search' not in tools — lenient should fall back.
        replayed = replay(original, tools={}, mode="lenient")
        calls = replayed.all_tool_calls()
        assert len(calls) >= 1
        search_calls = [c for c in calls if c.name == "search"]
        assert (
            search_calls[0].result == "recorded_result"
        ), "Lenient mode should use recorded result for unknown tool."

    def test_lenient_mode_records_warning_for_unknown_tool(self) -> None:
        """Fault detected: lenient mode silently drops unknown tool instead of warning."""
        original = _make_run_with_tool_calls(tool_results={"mystery_tool": "value"})
        replayed = replay(original, tools={}, mode="lenient")
        warnings = replayed.metadata.get("replay_warnings", [])
        assert any(
            "mystery_tool" in w for w in warnings
        ), "Lenient mode should warn when a tool is not found."


class TestInvalidMode:
    """Fault detected: unknown mode accepted silently."""

    def test_invalid_mode_raises(self) -> None:
        """An unrecognised mode must raise ValueError, not silently do nothing."""
        original = _make_run_with_tool_calls()
        with pytest.raises(ValueError, match="Unknown replay mode"):
            replay(original, tools={}, mode="invalid")  # type: ignore[arg-type]
