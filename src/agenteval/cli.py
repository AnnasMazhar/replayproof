"""Command-line interface for agenteval.

Commands:
    record   — run an agent and save the transcript
    replay   — replay a saved transcript
    run      — run a contract against a transcript
    gate     — compare current metrics to a baseline
    drift    — diff two suite results
    report   — render a suite result as markdown or HTML

All commands support --format json|md.
"""

from __future__ import annotations

import argparse
import json
import sys


def _cmd_record(args: argparse.Namespace) -> int:
    """Record an agent run from a Python module entry point.

    The --agent argument must be a dotted module path followed by a colon and
    the callable name: ``mypackage.agent:run_agent``.  The callable must have
    the signature ``(task: str, tools: dict) -> str``.  The ``tools`` dict
    passed to it will be empty; the callable is expected to construct its own
    tools internally.

    Example::

        agenteval record \\
            --agent examples.research_agent:research_agent \\
            --task "How do solar panels work" \\
            --output recordings/run.jsonl
    """
    import importlib
    import os

    from agenteval.record import Recorder

    module_path, _, fn_name = args.agent.partition(":")
    if not fn_name:
        print(
            f"error: --agent must be 'module.path:function_name', got {args.agent!r}\n"
            "Example: examples.research_agent:research_agent",
            file=sys.stderr,
        )
        return 1

    # Add cwd to sys.path so `--agent examples.research_agent:fn` works without
    # requiring the user to set PYTHONPATH=. explicitly.
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        print(
            f"error: cannot import module {module_path!r}: {exc}\n"
            "If the agent is a local module (not installed), add the repo root to PYTHONPATH:\n"
            "  PYTHONPATH=$(pwd) agenteval record --agent ...\n"
            "Or install the package: pip install -e .",
            file=sys.stderr,
        )
        return 1

    agent_fn = getattr(module, fn_name, None)
    if agent_fn is None:
        print(
            f"error: module {module_path!r} has no attribute {fn_name!r}.",
            file=sys.stderr,
        )
        return 1

    recorder = Recorder(agent=agent_fn, agent_id=args.agent)

    # Look for an optional ``build_tools()`` factory in the same module so the
    # agent can declare its own tool set without extra CLI flags.
    build_tools_fn = getattr(module, "build_tools", None)
    tools: dict = build_tools_fn() if callable(build_tools_fn) else {}

    run = recorder.record(task=args.task, tools=tools)

    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(run.to_jsonl() + "\n")

    if args.format == "json":
        print(json.dumps(run.to_dict(), indent=2))
    else:
        print(f"Recorded run: {run.name!r}")
        print(f"  turns       : {len(run.turns)}")
        print(f"  tool calls  : {len(run.all_tool_calls())}")
        print(f"  output      : {args.output}")
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    """Replay a saved JSONL run."""
    from agenteval.replay import replay
    from agenteval.transcript import Run

    try:
        with open(args.run, encoding="utf-8") as fh:
            line = fh.readline().strip()
    except FileNotFoundError:
        print(
            f"error: run file not found: {args.run!r}\n"
            "Check the path, or see examples/recordings/sample_run.jsonl for an example.",
            file=sys.stderr,
        )
        return 1

    try:
        run = Run.from_jsonl(line)
    except (KeyError, ValueError) as exc:
        print(
            f"error: cannot parse run from {args.run!r}: {exc}\n"
            "Each line must be a JSON object with at least 'name', 'turns', and "
            "'schema_version' fields.",
            file=sys.stderr,
        )
        return 1

    replayed = replay(run, tools={}, mode=args.mode)

    if args.format == "json":
        print(json.dumps(replayed.to_dict(), indent=2))
    else:
        print(f"Replayed: {replayed.name}")
        print(f"  turns: {len(replayed.turns)}")
        print(f"  tool_calls: {len(replayed.all_tool_calls())}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Evaluate a contract against one or more JSONL runs."""
    import os

    import yaml

    from agenteval.assertions import Contract
    from agenteval.scoring import CaseResult, compute_suite
    from agenteval.transcript import Run

    try:
        contract = Contract.from_yaml_file(args.contract)
    except FileNotFoundError:
        print(
            f"error: contract file not found: {args.contract!r}\n"
            "Check the path, or see examples/contracts/research.yaml for a template.",
            file=sys.stderr,
        )
        return 1
    except yaml.YAMLError as exc:
        print(
            f"error: could not parse YAML contract {args.contract!r}: {exc}\n"
            "Ensure each check is on its own line under 'checks:' and indented correctly.",
            file=sys.stderr,
        )
        return 1
    except (KeyError, TypeError) as exc:
        print(
            f"error: invalid contract structure in {args.contract!r}: {exc}\n"
            "Each check must have a 'type' field. See examples/contracts/research.yaml.",
            file=sys.stderr,
        )
        return 1

    case_results: list[CaseResult] = []
    run_files = args.runs if isinstance(args.runs, list) else [args.runs]

    for run_path in run_files:
        try:
            fh = open(run_path, encoding="utf-8")
        except FileNotFoundError:
            print(
                f"error: runs file not found: {run_path!r}\n"
                "Check the path, or see examples/recordings/sample_run.jsonl for an example.",
                file=sys.stderr,
            )
            return 1

        with fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    run = Run.from_jsonl(line)
                except (KeyError, ValueError) as exc:
                    print(
                        f"error: cannot parse run on line {lineno} of {run_path!r}: {exc}\n"
                        "Each line must be a JSON object with at least 'name', 'turns', and "
                        "'schema_version' fields. See examples/recordings/sample_run.jsonl.",
                        file=sys.stderr,
                    )
                    return 1
                check_results = contract.evaluate(run)
                case_results.append(
                    CaseResult(
                        case_id=run.name,
                        passed=check_results.passed,
                        checks=check_results,
                        tokens_in=run.total_tokens_in,
                        tokens_out=run.total_tokens_out,
                        latency_ms=run.total_latency_ms,
                    )
                )

    suite_name = os.path.basename(args.contract).replace(".yaml", "")
    suite = compute_suite(case_results, suite_name=suite_name)

    if args.format == "json":
        print(json.dumps(suite.to_dict(), indent=2))
    else:
        from agenteval.report import to_markdown

        print(to_markdown(suite))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(suite.to_dict(), fh, indent=2)

    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    """Compare current suite result to a baseline; exit 1 on trip."""
    from agenteval.budget import Baseline, Tolerances, compare

    try:
        with open(args.current, encoding="utf-8") as fh:
            current = json.load(fh)
    except FileNotFoundError:
        print(
            f"error: current result file not found: {args.current!r}\n"
            "Run 'agenteval run --output <file>' first to generate it.",
            file=sys.stderr,
        )
        return 1
    except json.JSONDecodeError as exc:
        # Detect the common mistake of passing a JSONL recording instead of a JSON result.
        is_likely_jsonl = args.current.endswith(".jsonl") or "extra data" in str(exc).lower()
        if is_likely_jsonl:
            print(
                f"error: {args.current!r} is not a valid JSON suite result.\n"
                "The --current argument must be a JSON file produced by"
                " 'agenteval run --output'.\n"
                "If you passed a JSONL recording, run it through the contract first:\n"
                "  agenteval run --contract <contract.yaml>"
                " --runs <recording.jsonl> --output <result.json>\n"
                "Then pass the result.json to 'agenteval gate --current result.json'.",
                file=sys.stderr,
            )
        else:
            print(
                f"error: {args.current!r} is not valid JSON: {exc}",
                file=sys.stderr,
            )
        return 1

    try:
        baseline = Baseline.from_file(args.baseline)
    except FileNotFoundError:
        print(
            f"error: baseline file not found: {args.baseline!r}\n"
            "Run 'agenteval run --output <baseline_file>' on a known-good run and commit it.",
            file=sys.stderr,
        )
        return 1
    except (json.JSONDecodeError, KeyError) as exc:
        print(
            f"error: cannot read baseline {args.baseline!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        gate = compare(current, baseline, Tolerances())
    except ValueError as exc:
        # Exit 2 (not 1): a NaN/inf metric is a corrupted input file, not a
        # measured regression, and must never be scored as a pass either.
        print(f"error: cannot score gate: {exc}", file=sys.stderr)
        print("error: gate metrics must be finite numbers", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(gate.to_dict(), indent=2))
    else:
        if gate.ok:
            print("Gate: PASS — no regressions detected.")
        else:
            print("Gate: FAIL — regressions detected:")
            print(f"{'Metric':<25} {'Baseline':>12} {'Current':>12} {'Threshold':>12}")
            print("-" * 65)
            for t in gate.trips:
                print(
                    f"{t.metric:<25} {t.baseline_value:>12.4f} "
                    f"{t.current_value:>12.4f} {t.threshold:>12.4f}"
                )
        if gate.skipped_zero_baseline:
            print(
                "Warning: the following gates were not enforced because the "
                "baseline value is zero (first-run or corrupted baseline): "
                + ", ".join(gate.skipped_zero_baseline)
            )

    return 0 if gate.ok else 1


def _cmd_drift(args: argparse.Namespace) -> int:
    """Compute drift between two suite result files."""
    from agenteval.drift import drift

    for label, path in (("--a", args.a), ("--b", args.b)):
        try:
            open(path, encoding="utf-8").close()
        except FileNotFoundError:
            print(
                f"error: suite file not found for {label}: {path!r}\n"
                "Run 'agenteval run --output <file>' to generate a suite result first.",
                file=sys.stderr,
            )
            return 1

    try:
        with open(args.a, encoding="utf-8") as fh:
            a_data = json.load(fh)
    except json.JSONDecodeError as exc:
        print(
            f"error: {args.a!r} is not valid JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        with open(args.b, encoding="utf-8") as fh:
            b_data = json.load(fh)
    except json.JSONDecodeError as exc:
        print(
            f"error: {args.b!r} is not valid JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    report = drift(a_data, b_data)

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"Regressions : {len(report.regressions)}")
        print(f"Fixes       : {len(report.fixes)}")
        print(f"Churn       : {len(report.churns)}")
        print(f"Stable pass : {len(report.stable_passes)}")
        print(f"Stable fail : {len(report.stable_fails)}")
        print(f"Token delta : {report.token_delta_total:+d}")
        if report.regressions:
            print("\nRegressions:")
            for cd in report.regressions:
                print(f"  {cd.case_id}")

    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    """Render a suite result as markdown or HTML."""
    from agenteval.report import to_html, to_markdown
    from agenteval.scoring import SuiteResult

    try:
        with open(args.suite, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(
            f"error: suite file not found: {args.suite!r}\n"
            "Run 'agenteval run --output <file>' to generate a suite result first.",
            file=sys.stderr,
        )
        return 1
    except json.JSONDecodeError as exc:
        print(
            f"error: {args.suite!r} is not valid JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    # Reconstruct a minimal SuiteResult from the dict.
    from agenteval.assertions import CheckResults
    from agenteval.scoring import CaseResult

    cases = []
    for c in data.get("cases", []):
        cases.append(
            CaseResult(
                case_id=c["case_id"],
                passed=c.get("passed", False),
                checks=CheckResults(results=()),
                tokens_in=c.get("tokens_in", 0),
                tokens_out=c.get("tokens_out", 0),
                latency_ms=c.get("latency_ms", 0.0),
            )
        )

    suite = SuiteResult(
        suite_name=data.get("suite_name", ""),
        case_results=tuple(cases),
        pass_rate_value=data.get("pass_rate", 0.0),
        wilson_lower_bound=data.get("wilson_lower", 0.0),
        total_tokens_in=data.get("total_tokens_in", 0),
        total_tokens_out=data.get("total_tokens_out", 0),
        total_cost_usd=data.get("total_cost_usd", 0.0),
        p50_latency_ms=data.get("p50_latency_ms", 0.0),
        p95_latency_ms=data.get("p95_latency_ms", 0.0),
    )

    if args.format == "html":
        output = to_html(suite)
    else:
        output = to_markdown(suite)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"Report written to {args.output}")
    else:
        print(output)

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="agenteval",
        description="Deterministic, offline-replayable regression testing for LLM agents.",
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    subs = parser.add_subparsers(dest="command")

    # record
    rec = subs.add_parser("record", help="Record an agent run")
    rec.add_argument("--agent", required=True, help="Agent module:function")
    rec.add_argument("--task", required=True, help="Task string")
    rec.add_argument("--output", required=True, help="Output JSONL path")
    rec.add_argument("--format", choices=["json", "md"], default="md")

    # replay
    rep = subs.add_parser("replay", help="Replay a recorded run")
    rep.add_argument("--run", required=True, help="JSONL run file")
    rep.add_argument(
        "--mode",
        choices=["strict", "lenient", "dry"],
        default="dry",
        help="Replay mode",
    )
    rep.add_argument("--format", choices=["json", "md"], default="md")

    # run
    run_p = subs.add_parser("run", help="Evaluate a contract against runs")
    run_p.add_argument("--contract", required=True, help="YAML contract file")
    run_p.add_argument("--runs", nargs="+", required=True, help="JSONL run files")
    run_p.add_argument("--output", help="Write suite result JSON to this file")
    run_p.add_argument("--format", choices=["json", "md"], default="md")

    # gate
    gate_p = subs.add_parser("gate", help="Compare current to baseline")
    gate_p.add_argument("--baseline", required=True, help="Baseline JSON file")
    gate_p.add_argument("--current", required=True, help="Current suite JSON file")
    gate_p.add_argument("--format", choices=["json", "md"], default="md")

    # drift
    drift_p = subs.add_parser("drift", help="Diff two suite results")
    drift_p.add_argument("--a", required=True, help="Suite result A (JSON)")
    drift_p.add_argument("--b", required=True, help="Suite result B (JSON)")
    drift_p.add_argument("--format", choices=["json", "md"], default="md")

    # report
    report_p = subs.add_parser("report", help="Render a suite result")
    report_p.add_argument("--suite", required=True, help="Suite result JSON file")
    report_p.add_argument("--output", help="Write output to file")
    report_p.add_argument("--format", choices=["json", "md", "html"], default="md")

    return parser


def main() -> None:
    """Entry point for the agenteval CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if getattr(args, "version", False):
        import agenteval

        print(agenteval.__version__)
        return

    dispatch = {
        "record": _cmd_record,
        "replay": _cmd_replay,
        "run": _cmd_run,
        "gate": _cmd_gate,
        "drift": _cmd_drift,
        "report": _cmd_report,
    }

    if args.command is None:
        parser.print_help()
        return

    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(fn(args))


if __name__ == "__main__":
    main()
