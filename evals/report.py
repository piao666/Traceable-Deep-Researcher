"""Summarize existing engineering replay results without regenerating research."""

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.out.exists():
            raise ValueError("output directory already exists")
        lines = ["# Engineering replay summary", "", "evaluation_kind: engineering_replay",
                 "", "These are frozen fixture checks, not live research quality scores.", "",
                 "| Suite | Cases | Passed | Failed | Error |", "|---|---:|---:|---:|---:|"]
        for directory in args.runs:
            summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
            if summary["evaluation_kind"] != "engineering_replay":
                raise ValueError("incompatible evaluation kind")
            states = summary["case_states"]
            lines.append(f"| {summary['suite']} | {summary['case_count']} | {states['passed']} | {states['failed']} | {states['error']} |")
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"report error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
