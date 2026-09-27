"""Convert an Inspect AI .eval log to replayproof JSONL.

Usage:
    python scripts/convert_inspect_log.py <path/to/eval.eval> <path/to/output.jsonl>

An Inspect .eval file is a ZIP archive containing log.json.  Each sample in
log.json is converted to one replayproof Run and written as a JSONL line.

The converter reads only the fields replayproof uses:
  - sample["id"]             -> Run.name
  - eval["model"]            -> Run.model
  - each model event's output.choices[*].message -> turns

This is a best-effort converter.  Samples that produce no messages are skipped
with a warning.

Example:
    python scripts/convert_inspect_log.py logs/my_eval.eval recordings/my_eval.jsonl
    agenteval run --contract contracts/research.yaml \\
                  --runs recordings/my_eval.jsonl \\
                  --output baseline.json
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

from agenteval.record import from_messages
from agenteval.transcript import Run


def convert(eval_path: str, out_path: str) -> None:
    """Convert an Inspect AI .eval archive to a replayproof JSONL file.

    Args:
        eval_path: Path to the Inspect .eval ZIP archive.
        out_path: Destination path for the replayproof JSONL file.
    """
    runs: list[Run] = []
    with zipfile.ZipFile(eval_path) as z:
        with z.open("log.json") as f:
            log = json.load(f)

    model = log.get("eval", {}).get("model", "unknown")

    for sample in log.get("samples", []):
        messages: list[dict] = []
        for event in sample.get("events", []):
            if event.get("event") == "model":
                for choice in event.get("output", {}).get("choices", [{}]):
                    msg = choice.get("message", {})
                    if msg:
                        messages.append(msg)
        if not messages:
            sample_id = sample.get("id", "?")
            print(
                f"  warning: sample {sample_id!r} produced no messages — skipped",
                file=sys.stderr,
            )
            continue
        runs.append(
            from_messages(
                messages,
                name=str(sample.get("id", "unknown")),
                model=model,
            )
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for run in runs:
            fh.write(run.to_jsonl() + "\n")

    print(f"Wrote {len(runs)} runs to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/convert_inspect_log.py <eval_path> <out_path>",
            file=sys.stderr,
        )
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
