"""Validate checked-in offline evaluation fixtures without contacting providers."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.framework.datasets import load_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path,
                        default=ROOT / "evals/datasets/dataset_manifest.json")
    args = parser.parse_args(argv)
    try:
        dataset = load_dataset(args.manifest)
    except ValueError as error:
        print(json.dumps({"valid": False, "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({"valid": True, "task_cases": len(dataset.tasks), "agent_cases": len(dataset.agents),
                      "dataset_hash": dataset.dataset_hash, "source_hash": dataset.source_hash}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
