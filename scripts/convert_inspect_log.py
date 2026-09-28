"""Convert an Inspect AI .eval log to replayproof JSONL.

Inspect .eval files are zip archives. Two layouts exist in the wild:
  - current (verified against inspect_ai main, 2026-09-27): header.json plus
    one samples/<id>.json member per sample;
  - legacy: a single log.json with an inline "samples" array.

Both layouts are handled. Each sample's model events are normalised to
replayproof's OpenAI-style message format, then one Run per sample is written.

Usage:
    python scripts/convert_inspect_log.py <path/to/eval.eval> <output_dir/>

The output JSONL file is placed in <output_dir/> with the same stem as the
.eval file plus a .jsonl extension.
"""

import json
import sys
import zipfile
from pathlib import Path

from agenteval.record import from_messages
from agenteval.transcript import Run


def _load(eval_path: str) -> tuple[dict, list[dict]]:
    """Return (header, samples) for either archive layout.

    Legacy layout: single log.json with {"samples": [...], "eval": {...}}.
    Current layout: header.json + samples/<id>.json per sample.
    """
    with zipfile.ZipFile(eval_path) as z:
        names = z.namelist()
        if "log.json" in names:
            with z.open("log.json") as f:
                log = json.load(f)
            return log, log.get("samples", [])
        header = json.loads(z.read("header.json")) if "header.json" in names else {}
        samples = [json.loads(z.read(n)) for n in sorted(names) if n.startswith("samples/")]
        return header, samples


def convert(eval_path: str, out_dir: str) -> None:
    """Convert a single .eval archive to a replayproof JSONL file.

    Parameters
    ----------
    eval_path:
        Path to an Inspect AI .eval archive (a zip file).
    out_dir:
        Directory to write the resulting JSONL file into.
        Created if it does not exist.
    """
    out = Path(out_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=True)

    header, samples = _load(eval_path)
    runs: list[Run] = []
    for sample in samples:
        messages: list[dict] = []
        for event in sample.get("events", []):
            if event.get("event") != "model":
                continue
            usage = event.get("output", {}).get("usage") or {}
            for msg in event.get("output", {}).get("choices", [{}]):
                content = dict(msg.get("message", {}))
                # Propagate token counts from the usage block when not already present.
                if usage and "tokens_in" not in content:
                    content["tokens_in"] = usage.get("input_tokens", 0)
                    content["tokens_out"] = usage.get("output_tokens", 0)
                messages.append(content)
        if not messages:
            sample_id = sample.get("id", "?")
            print(
                f"  warning: sample {sample_id!r} produced no messages — skipped",
                file=sys.stderr,
            )
            continue
        run = from_messages(
            messages,
            name=str(sample.get("id", "unknown")),
            agent_id="inspect-agent",
            model=header.get("eval", {}).get("model", "unknown"),
            provider="inspect",
        )
        runs.append(run)

    out_file = (out / Path(eval_path).stem).with_suffix(".jsonl")
    with open(out_file, "w") as f:
        for run in runs:
            f.write(run.to_jsonl() + "\n")
    print(f"Wrote {len(runs)} runs to {out_file}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/convert_inspect_log.py <eval_path> <out_dir>",
            file=sys.stderr,
        )
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
