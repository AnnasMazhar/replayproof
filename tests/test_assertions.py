"""Tests for assertion checks against good and deliberately bad runs.

Faults detected by each test class and method:

TestToolSequenceCheck:
- test_passes_on_correct_sequence: catches a check that always returns failure.
- test_fails_on_wrong_order: catches a check that ignores ordering constraint.
- test_fails_on_missing_tool_in_sequence: catches a check that returns pass when
  a required tool is absent.
- test_unordered_mode_passes_despite_order: catches a check that enforces order when
  ordered=False was set.

TestRequiredToolsCheck:
- test_passes_when_all_present: catches always-fail implementation.
- test_fails_when_tool_missing: catches a check that ignores the names list.

TestForbiddenToolsCheck:
- test_passes_when_none_called: catches always-fail implementation.
- test_fails_when_forbidden_tool_called: catches a check that ignores the names list.

TestArgSchemaCheck:
- test_passes_on_valid_args: catches a check that always fails.
- test_fails_on_invalid_args: catches a check that ignores schema validation.

TestMaxToolCallsCheck:
- test_passes_within_limit: catches always-fail.
- test_fails_over_limit: catches a check that does not count calls correctly.

TestMaxTokensCheck:
- test_passes_within_limit: catches always-fail.
- test_fails_over_limit: catches a check that does not sum tokens.

TestNoPatternCheck:
- test_passes_no_match: catches always-fail.
- test_fails_on_email_match: catches a check that ignores regex matching.
  Specifically tests the email PII case, which is the hostile-user scenario.

TestFinalAnswerNotEmptyCheck:
- test_passes_nonempty: catches always-fail.
- test_fails_empty: catches a check that ignores whitespace-only content.

TestFinalAnswerMatchesCheck:
- test_passes_matching: catches always-fail.
- test_fails_not_matching: catches always-pass.

TestContractYAML:
- test_yaml_round_trip: catches a YAML serialiser that loses check type or fields.
- test_contract_evaluate_aggregate_pass: integration test catching a Contract that
  evaluates checks in wrong order or ignores a check.
- test_contract_evaluate_aggregate_fail: integration test catching a Contract that
  returns passed=True even when an error check failed.

TestHostileInputs:
- test_injection_string_in_content: a naive implementation might throw on regex
  metacharacters in agent content; this test catches that.
- test_huge_tool_call_count: catches off-by-one or OOM on very large call counts.
- test_unicode_in_content: catches a no_pattern check that crashes on non-ASCII.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agenteval.assertions import (
    ArgSchemaCheck,
    Contract,
    FinalAnswerMatchesCheck,
    FinalAnswerNotEmptyCheck,
    ForbiddenToolsCheck,
    MaxTokensCheck,
    MaxToolCallsCheck,
    NoPatternCheck,
    RequiredToolsCheck,
    ToolSequenceCheck,
)
from agenteval.transcript import Run, ToolCall, Turn


def _run(
    tool_names: list[str] | None = None,
    final_content: str = "Done.",
    tokens_in: int = 100,
    tokens_out: int = 50,
    latency_ms: float = 200.0,
    args_per_tool: dict | None = None,
) -> Run:
    """Build a minimal Run for assertion testing."""
    if tool_names is None:
        tool_names = []
    if args_per_tool is None:
        args_per_tool = {}

    tool_calls = tuple(
        ToolCall(
            name=name,
            args=args_per_tool.get(name, {"q": "x"}),
            result="ok",
        )
        for name in tool_names
    )
    return Run(
        name="test",
        agent_id="agent",
        model="none",
        provider="local",
        started_at="2026-01-01T00:00:00Z",
        turns=(
            Turn(role="user", content="question"),
            Turn(
                role="assistant",
                content=final_content,
                tool_calls=tool_calls,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            ),
        ),
        total_tokens_in=tokens_in,
        total_tokens_out=tokens_out,
        total_latency_ms=latency_ms,
    )


class TestToolSequenceCheck:
    def test_passes_on_correct_sequence(self) -> None:
        """Fault: check always returns failure even for correct sequence."""
        check = ToolSequenceCheck(expected=["search", "summarise"], ordered=True)
        r = check.evaluate(_run(tool_names=["search", "summarise"]))
        assert r.passed, r.message

    def test_fails_on_wrong_order(self) -> None:
        """Fault: check ignores ordering and passes reversed sequence."""
        check = ToolSequenceCheck(expected=["search", "summarise"], ordered=True)
        r = check.evaluate(_run(tool_names=["summarise", "search"]))
        assert not r.passed, "Must fail when required order is reversed"

    def test_fails_on_missing_tool_in_sequence(self) -> None:
        """Fault: check passes when a required tool is absent."""
        check = ToolSequenceCheck(expected=["search", "summarise"], ordered=True)
        r = check.evaluate(_run(tool_names=["search"]))
        assert not r.passed, "Must fail when 'summarise' is absent"

    def test_unordered_mode_passes_despite_order(self) -> None:
        """Fault: check enforces order in unordered mode."""
        check = ToolSequenceCheck(expected=["search", "summarise"], ordered=False)
        r = check.evaluate(_run(tool_names=["summarise", "search"]))
        assert r.passed, r.message


class TestRequiredToolsCheck:
    def test_passes_when_all_present(self) -> None:
        """Fault: check always fails."""
        check = RequiredToolsCheck(names=["search"])
        r = check.evaluate(_run(tool_names=["search", "other"]))
        assert r.passed, r.message

    def test_fails_when_tool_missing(self) -> None:
        """Fault: check ignores names list."""
        check = RequiredToolsCheck(names=["search", "summarise"])
        r = check.evaluate(_run(tool_names=["search"]))
        assert not r.passed, "Must fail when 'summarise' is missing"
        assert "summarise" in r.message


class TestForbiddenToolsCheck:
    def test_passes_when_none_called(self) -> None:
        """Fault: check always fails."""
        check = ForbiddenToolsCheck(names=["dangerous_tool"])
        r = check.evaluate(_run(tool_names=["safe_tool"]))
        assert r.passed, r.message

    def test_fails_when_forbidden_tool_called(self) -> None:
        """Fault: check ignores names list."""
        check = ForbiddenToolsCheck(names=["dangerous_tool"])
        r = check.evaluate(_run(tool_names=["dangerous_tool"]))
        assert not r.passed, "Must fail when forbidden tool is called"
        assert "dangerous_tool" in r.message


class TestArgSchemaCheck:
    def test_passes_on_valid_args(self) -> None:
        """Fault: check always fails schema validation."""
        schema = {"type": "object", "properties": {"q": {"type": "string"}}}
        check = ArgSchemaCheck(tool="search", schema=schema)
        r = check.evaluate(
            _run(
                tool_names=["search"],
                args_per_tool={"search": {"q": "solar panels"}},
            )
        )
        assert r.passed, r.message

    def test_fails_on_invalid_args(self) -> None:
        """Fault: check ignores schema, always passes."""
        schema = {
            "type": "object",
            "required": ["q"],
            "properties": {"q": {"type": "string"}},
            "additionalProperties": False,
        }
        check = ArgSchemaCheck(tool="search", schema=schema)
        r = check.evaluate(
            _run(
                tool_names=["search"],
                args_per_tool={"search": {"wrong_key": 42}},
            )
        )
        assert not r.passed, "Must fail when args don't match schema"


class TestMaxToolCallsCheck:
    def test_passes_within_limit(self) -> None:
        """Fault: check always fails."""
        check = MaxToolCallsCheck(n=5)
        r = check.evaluate(_run(tool_names=["a", "b", "c"]))
        assert r.passed, r.message

    def test_fails_over_limit(self) -> None:
        """Fault: check does not count calls correctly."""
        check = MaxToolCallsCheck(n=2)
        r = check.evaluate(_run(tool_names=["a", "b", "c"]))
        assert not r.passed, "Must fail when 3 calls exceed limit of 2"

    def test_passes_exactly_at_limit(self) -> None:
        """Fault: check uses strict > instead of >=."""
        check = MaxToolCallsCheck(n=3)
        r = check.evaluate(_run(tool_names=["a", "b", "c"]))
        assert r.passed, "Must pass when count equals limit"


class TestMaxTokensCheck:
    def test_passes_within_limit(self) -> None:
        """Fault: check always fails."""
        check = MaxTokensCheck(n=200)
        r = check.evaluate(_run(tokens_in=50, tokens_out=50))
        assert r.passed, r.message

    def test_fails_over_limit(self) -> None:
        """Fault: check ignores tokens or does not sum in+out."""
        check = MaxTokensCheck(n=99)
        r = check.evaluate(_run(tokens_in=50, tokens_out=50))
        assert not r.passed, "Must fail when 100 total tokens exceeds limit of 99"


class TestNoPatternCheck:
    def test_passes_no_match(self) -> None:
        """Fault: check always fails."""
        check = NoPatternCheck(
            field_name="final_content",
            regex=r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        )
        r = check.evaluate(_run(final_content="No emails here."))
        assert r.passed, r.message

    def test_fails_on_email_match(self) -> None:
        """Fault: check ignores regex or field.

        This is the hostile-user case: an email address is present in the
        final content and must trigger the no_pattern check.
        """
        check = NoPatternCheck(
            field_name="final_content",
            regex=r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        )
        r = check.evaluate(_run(final_content="Contact: user@example.com for info."))
        assert not r.passed, "Must fail when email address is present in final content"

    def test_passes_tool_args_no_match(self) -> None:
        """Fault: field_name='tool_args' selection is broken."""
        check = NoPatternCheck(field_name="tool_args", regex=r"secret")
        r = check.evaluate(
            _run(
                tool_names=["search"],
                args_per_tool={"search": {"q": "normal query"}},
            )
        )
        assert r.passed, r.message

    def test_fails_tool_args_with_secret(self) -> None:
        """Fault: tool_args field not checked."""
        check = NoPatternCheck(field_name="tool_args", regex=r"secret")
        r = check.evaluate(
            _run(
                tool_names=["search"],
                args_per_tool={"search": {"q": "my secret key"}},
            )
        )
        assert not r.passed, "Must fail when 'secret' appears in tool args"


class TestFinalAnswerNotEmptyCheck:
    def test_passes_nonempty(self) -> None:
        """Fault: check always fails."""
        check = FinalAnswerNotEmptyCheck()
        r = check.evaluate(_run(final_content="Here is the answer."))
        assert r.passed, r.message

    def test_fails_empty(self) -> None:
        """Fault: check accepts empty string."""
        check = FinalAnswerNotEmptyCheck()
        r = check.evaluate(_run(final_content=""))
        assert not r.passed, "Must fail on empty final answer"

    def test_fails_whitespace_only(self) -> None:
        """Fault: check does not strip whitespace."""
        check = FinalAnswerNotEmptyCheck()
        r = check.evaluate(_run(final_content="   \n  "))
        assert not r.passed, "Must fail on whitespace-only final answer"


class TestFinalAnswerMatchesCheck:
    def test_passes_matching(self) -> None:
        """Fault: check always fails."""
        check = FinalAnswerMatchesCheck(regex=r"answer")
        r = check.evaluate(_run(final_content="The answer is 42."))
        assert r.passed, r.message

    def test_fails_not_matching(self) -> None:
        """Fault: check always passes regardless of content."""
        check = FinalAnswerMatchesCheck(regex=r"^\d{4}-\d{2}-\d{2}$")
        r = check.evaluate(_run(final_content="Not a date."))
        assert not r.passed, "Must fail when content does not match regex"


class TestContractYAML:
    def test_yaml_round_trip(self) -> None:
        """Fault: YAML serialiser loses check type or fields."""
        yaml_text = """
name: test_contract
checks:
  - type: required_tools
    id: required_tools
    severity: error
    names:
      - search
  - type: max_tool_calls
    id: max_tool_calls
    severity: error
    n: 5
"""
        contract = Contract.from_yaml(yaml_text)
        assert contract.name == "test_contract"
        assert len(contract.checks) == 2
        assert contract.checks[0].id == "required_tools"
        assert contract.checks[1].id == "max_tool_calls"

    def test_contract_evaluate_aggregate_pass(self) -> None:
        """Fault: Contract skips a check or returns wrong aggregate."""
        yaml_text = """
name: all_pass
checks:
  - type: required_tools
    id: required_tools
    severity: error
    names:
      - search
  - type: final_answer_not_empty
    id: final_answer_not_empty
    severity: error
"""
        contract = Contract.from_yaml(yaml_text)
        run = _run(tool_names=["search"], final_content="Found it.")
        results = contract.evaluate(run)
        assert results.passed, f"Should pass; errors: {results.errors}"

    def test_contract_evaluate_aggregate_fail(self) -> None:
        """Fault: Contract returns passed=True even when an error check failed."""
        yaml_text = """
name: will_fail
checks:
  - type: required_tools
    id: required_tools
    severity: error
    names:
      - search
  - type: final_answer_not_empty
    id: final_answer_not_empty
    severity: error
"""
        contract = Contract.from_yaml(yaml_text)
        # Missing required tool 'search'.
        run = _run(tool_names=[], final_content="Found it.")
        results = contract.evaluate(run)
        assert not results.passed, "Contract should fail when required tool is missing"
        assert len(results.errors) == 1


class TestHostileInputs:
    """Adversarial inputs: a naive implementation would fail at least one of these."""

    def test_injection_string_in_content(self) -> None:
        """Fault: regex compilation crashes on metacharacters in agent content.

        The content below contains regex metacharacters. The check should apply
        its own regex to this content without crashing.
        """
        check = FinalAnswerMatchesCheck(regex=r"safe")
        # Content has regex metacharacters: [, (, *, +, ?.
        hostile = r"[injection] (try) to **break** regex+parsing?!"
        r = check.evaluate(_run(final_content=hostile))
        assert not r.passed  # "safe" not in hostile content

    def test_huge_tool_call_count(self) -> None:
        """Fault: off-by-one or OOM when counting very large number of tool calls."""
        check = MaxToolCallsCheck(n=999)
        run = _run(tool_names=["tool"] * 1000)
        r = check.evaluate(run)
        assert not r.passed, "Must fail when 1000 calls exceed limit of 999"

    def test_unicode_in_content(self) -> None:
        """Fault: no_pattern check crashes on non-ASCII content."""
        check = NoPatternCheck(
            field_name="final_content",
            regex=r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
        )
        unicode_content = "Ответ: нет электронной почты. \u4e2d\u6587\u5185\u5bb9."
        r = check.evaluate(_run(final_content=unicode_content))
        assert r.passed, f"Should pass; no email in unicode content. Error: {r.message}"

    def test_empty_run_no_tool_calls(self) -> None:
        """Fault: various checks crash on a Run with no turns or no tool calls."""
        check = RequiredToolsCheck(names=["search"])
        # A run with no tool calls.
        r = check.evaluate(_run(tool_names=[]))
        assert not r.passed

    def test_max_tokens_zero_limit(self) -> None:
        """Fault: max_tokens check with n=0 crashes or incorrectly passes."""
        check = MaxTokensCheck(n=0)
        r = check.evaluate(_run(tokens_in=1, tokens_out=0))
        assert not r.passed, "Any token usage should exceed a 0-token limit"
