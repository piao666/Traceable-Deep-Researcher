"""Run engineering replay, without importing research/provider entry points."""

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from evals.framework.manifest import create_manifest
from evals.framework.constraints import json_values_equal
from evals.framework.models import AgentCase, EvalResult, TaskCase
from evals.framework.network_guard import offline_network
from evals.framework.replay import ToolReplay
from evals.framework.results import aggregate_results
from evals.quality_eval.metrics import citation_faithfulness

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _check(name: str, valid: bool, reason: str = "") -> EvalResult:
    return EvalResult(name=name, status="passed" if valid else "failed", score=float(valid), reason=reason)


def run_case(case: TaskCase | AgentCase, suite: str, replays: dict) -> dict:
    """Replay tool/model artifacts and check engineering contracts, not truth."""
    replay = ToolReplay(replays["tools"])
    started = time.monotonic()
    output = None
    metrics = []
    try:
        tools = []

        def call(tool, args, key):
            if replay.calls >= case.budget.max_tool_calls or time.monotonic() - started > case.budget.max_seconds:
                raise RuntimeError("replay budget exceeded")
            return replay.call(tool, args, context=case.case_id, fixture_key=key)

        for request in replays[suite][case.replay_key]["calls"]:
            if isinstance(case, AgentCase) and request["tool_name"] not in case.allowed_tools:
                raise ValueError("node attempted a tool outside allowed_tools")
            tools.append(call(request["tool_name"], request["arguments"], request["fixture_key"]))
        output = call("fixture.model" if suite == "task" else "fixture.node",
                      {"input": case.agent_input(), "tool_results": tools}, "output")
        if not isinstance(output, dict):
            raise ValueError("fixture output must be a JSON object")
        if isinstance(case, TaskCase):
            report = output.get("report")
            sources = output.get("sources")
            metrics += [_check("report_nonempty", isinstance(report, str) and bool(report.strip())),
                        _check("sources_schema", isinstance(sources, list) and all(isinstance(x, str) for x in sources))]
            if isinstance(report, str) and isinstance(sources, list) and all(isinstance(x, str) for x in sources):
                raw = citation_faithfulness(report, sources)
                score = raw["citation_faithfulness"]
                metrics.append(EvalResult(name="legacy_domain_reference_alignment",
                                           status="not_applicable" if score is None else "passed",
                                           score=score, reason="No reference domains" if score is None else
                                           "Descriptive domain alignment; not semantic citation support",
                                           breakdown=raw))
        else:
            keys = case.expected_constraints.get("required_keys", [])
            metrics.append(_check("node_output_keys", all(key in output for key in keys)))
            for key, value in case.expected_constraints.get("equals", {}).items():
                metrics.append(_check("node_expected_" + key, key in output and json_values_equal(output[key], value)))
    except Exception as exc:
        metrics.append(EvalResult(name="execution", status="error", reason=f"{type(exc).__name__}: {exc}"))
    states = {r.status for r in metrics}
    status = "error" if "error" in states else "failed" if "failed" in states else "passed"
    return {"case_id": case.case_id, "suite": suite, "status": status,
            "metrics": [r.model_dump(mode="json") for r in metrics], "output": output,
            "fixture_calls": replay.calls, "provider_calls": 0}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("task", "agent"), required=True)
    parser.add_argument("--mode", choices=("offline", "frozen-tools", "live"), default=os.getenv("TDR_EVAL_MODE", "offline"))
    parser.add_argument("--manifest", type=Path, default=ROOT / "evals/datasets/dataset_manifest.json")
    parser.add_argument("--split", choices=("dev", "calibration", "holdout"), default="dev")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode != "offline":
            raise ValueError("M0 only supports offline mode; online providers are not enabled")
        if args.limit is not None and args.limit <= 0:
            raise ValueError("limit must be positive")
        if args.out.exists():
            raise ValueError("output directory already exists; choose a new run directory")
        from evals.framework.datasets import load_dataset
        with offline_network():
            dataset = load_dataset(args.manifest)
            cases = [c for c in (dataset.tasks if args.suite == "task" else dataset.agents) if c.split == args.split]
            if args.limit is not None:
                cases = cases[:args.limit]
            if not cases:
                raise ValueError("no cases selected")
            results = [run_case(case, args.suite, dataset.replays) for case in cases]
        manifest = create_manifest(ROOT, dataset_hash=dataset.dataset_hash, source_hash=dataset.source_hash,
                                   config={"suite": args.suite, "split": args.split, "limit": args.limit},
                                   prompt_inputs={c.case_id: c.agent_input() for c in cases}, seed=args.seed)
        per_metric = defaultdict(list)
        for result in results:
            for metric in result["metrics"]:
                per_metric[metric["name"]].append(EvalResult(**metric))
        counts = Counter(r["status"] for r in results)
        summary = {"evaluation_kind": "engineering_replay", "suite": args.suite, "case_count": len(results),
                   "case_states": {key: counts[key] for key in ("passed", "failed", "error")},
                   "metrics": {name: aggregate_results(values) for name, values in sorted(per_metric.items())},
                   "provider_calls": 0, "known_cost_usd": 0}
        args.out.mkdir(parents=True, exist_ok=False)
        _write_json(args.out / "manifest.json", manifest)
        _write_json(args.out / "results.json", results)
        _write_json(args.out / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False))
        return 2 if counts["error"] else 1 if counts["failed"] else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"evaluation error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
