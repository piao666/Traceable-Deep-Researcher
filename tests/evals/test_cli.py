import json
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]


def cli(*args):
    return subprocess.run([sys.executable, "-m", "evals.run", *args], cwd=ROOT,
                          text=True, encoding="utf-8", capture_output=True,
                          env=os.environ | {"TDR_BLOCK_NETWORK": "1", "PYTHONUTF8": "1"}, timeout=30)


def test_offline_task_and_node_suites_and_report(tmp_path):
    for suite in ("task", "agent"):
        out = tmp_path / suite
        result = cli("--suite", suite, "--out", str(out))
        assert result.returncode == 0, result.stderr + result.stdout
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert summary["case_count"] == 8 and summary["case_states"]["passed"] == 8
        assert manifest["evaluation_kind"] == "engineering_replay"
        assert manifest["provider_calls"] == manifest["known_cost_usd"] == 0
        assert cli("--suite", suite, "--out", str(out)).returncode == 2
    report = subprocess.run([sys.executable, "-m", "evals.report", "--runs", str(tmp_path / "task"),
                             str(tmp_path / "agent"), "--out", str(tmp_path / "report")],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert report.returncode == 0, report.stderr
    text = (tmp_path / "report/summary.md").read_text(encoding="utf-8")
    assert "engineering_replay" in text


def test_online_modes_are_not_silently_enabled(tmp_path):
    result = cli("--suite", "task", "--mode", "live", "--out", str(tmp_path / "live"))
    assert result.returncode == 2
    assert not (tmp_path / "live").exists()


def test_invalid_limit_is_configuration_error(tmp_path):
    assert cli("--suite", "task", "--limit", "0", "--out", str(tmp_path / "out")).returncode == 2


def test_valid_negative_candidate_returns_failed_not_configuration_error(tmp_path):
    dataset = tmp_path / "dataset"
    shutil.copytree(ROOT / "evals/datasets", dataset)
    replay_path = dataset / "replays/replays.v1.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    # A valid JSON node output can be wrong: leave grading to the runner.
    next(record for record in replay["tools"] if record["tool_name"] == "fixture.node")["result"] = {}
    replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")
    manifest_path = dataset / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["replays/replays.v1.json"] = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "negative"
    result = cli("--suite", "agent", "--manifest", str(manifest_path), "--out", str(out))
    assert result.returncode == 1, result.stderr + result.stdout
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["case_states"] == {"passed": 7, "failed": 1, "error": 0}


def test_fixture_miss_is_recorded_as_execution_error():
    from evals.framework.datasets import load_dataset
    from evals.run import run_case

    dataset = load_dataset(ROOT / "evals/datasets/dataset_manifest.json")
    dataset.replays["tools"] = []
    outcome = run_case(dataset.tasks[0], "task", dataset.replays)
    assert outcome["status"] == "error"
    assert outcome["metrics"][-1]["status"] == "error"
    assert "FixtureMiss" in outcome["metrics"][-1]["reason"]
    assert outcome["provider_calls"] == 0


def test_node_boolean_constraint_does_not_accept_numeric_one():
    from evals.framework.datasets import load_dataset
    from evals.run import run_case

    dataset = load_dataset(ROOT / "evals/datasets/dataset_manifest.json")
    case = next(case for case in dataset.agents if "abstained" in case.expected_constraints.get("equals", {}))
    fixture = next(row for row in dataset.replays["tools"]
                   if row["tool_name"] == "fixture.node" and row["context"] == case.case_id)
    fixture["result"]["abstained"] = 1
    outcome = run_case(case, "agent", dataset.replays)
    assert outcome["status"] == "failed"
