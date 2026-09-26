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
    """Record an agent run from a Python module entry point."""
    print("record: load agent module and record a run", file=sys.stderr)
    print("Not yet wired to a live agent in this demo build.", file=sys.stderr)
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    """Replay a saved JSONL run."""
    from agenteval.replay import replay
    from agenteval.transcript import Run

    with open(args.run, encoding="utf-8") as fh:
        line = fh.readline().strip()
    run = Run.from_jsonl(line)
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

    from agenteval.assertions import Contract
    from agenteval.scoring import CaseResult, compute_suite
    from agenteval.transcript import Run

    contract = Contract.from_yaml_file(args.contract)

    case_results: list[CaseResult] = []
    run_files = args.runs if isinstance(args.runs, list) else [args.runs]

    for run_path in run_files:
        with open(run_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                run = Run.from_jsonl(line)
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

    with open(args.current, encoding="utf-8") as fh:
        current = json.load(fh)
    baseline = Baseline.from_file(args.baseline)
    gate = compare(current, baseline, Tolerances())

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

    return 0 if gate.ok else 1


def _cmd_drift(args: argparse.Namespace) -> int:
    """Compute drift between two suite result files."""
    from agenteval.drift import drift

    with open(args.a, encoding="utf-8") as fh:
        a_data = json.load(fh)
    with open(args.b, encoding="utf-8") as fh:
        b_data = json.load(fh)

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

    with open(args.suite, encoding="utf-8") as fh:
        data = json.load(fh)

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
