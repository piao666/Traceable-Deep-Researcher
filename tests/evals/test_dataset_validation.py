"""Dataset integrity failures must be rejected before any replay starts."""

import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

DATASET = Path(__file__).resolve().parents[2] / "evals" / "datasets"


def load(path):
    assert importlib.util.find_spec("evals.framework.datasets"), "dataset loader is required"
    from evals.framework.datasets import load_dataset
    return load_dataset(path)


@pytest.fixture
def manifest(tmp_path):
    target = tmp_path / "dataset"
    shutil.copytree(DATASET, target)
    return target / "dataset_manifest.json"


def mutate(manifest, filename, edit):
    path = manifest.parent / filename
    jsonl = path.suffix == ".jsonl"
    value = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if jsonl else json.loads(path.read_text(encoding="utf-8"))
    edit(value)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in value) + "\n" if jsonl else json.dumps(value, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    metadata["files"][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(metadata), encoding="utf-8")


def test_loads_bilingual_development_fixtures():
    dataset = load(DATASET / "dataset_manifest.json")
    assert len(dataset.tasks) == len(dataset.agents) == 8
    assert {case.split for case in dataset.tasks + dataset.agents} == {"dev"}
    assert {case.node_kind for case in dataset.agents} == {"planner", "retriever", "context_selector", "writer", "reviewer", "reviser", "mcp_selector", "orchestrator"}
    assert {"zh", "en"} <= {tag for case in dataset.tasks for tag in case.tags}
    assert len(dataset.dataset_hash) == len(dataset.source_hash) == 64


def test_fixture_suite_contains_repeated_citation_case():
    dataset = load(DATASET / "dataset_manifest.json")
    assert any("duplicate-citation" in case.tags for case in dataset.tasks)
    outputs = [row["result"] for row in dataset.replays["tools"] if row["tool_name"] == "fixture.model"]
    assert any(len(output["sources"]) > len(set(output["sources"])) for output in outputs)


def test_rejects_modified_bytes(manifest):
    with (manifest.parent / "task_cases.v1.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="hash"):
        load(manifest)


def test_rejects_path_escape(manifest):
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    metadata["task_cases"] = "../outside.jsonl"
    del metadata["files"]["task_cases.v1.jsonl"]
    metadata["files"]["../outside.jsonl"] = "0" * 64
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="path|outside|escape"):
        load(manifest)


@pytest.mark.parametrize("change, message", [
    (lambda rows: rows[1].update(case_id=rows[0]["case_id"]), "duplicate"),
    (lambda rows: rows[1].update(group_id=rows[0]["group_id"], split="holdout"), "split"),
    (lambda rows: rows[0].update(dataset_version="2"), "version"),
    (lambda rows: rows[0].update(source_bundle="absent"), "bundle"),
    (lambda rows: rows[0].update(gold_evidence=["absent"]), "evidence"),
    (lambda rows: rows[0].update(query=""), "query|validation"),
    (lambda rows: rows[0].update(schema_version=True), "schema|version"),
])
def test_rejects_invalid_task_semantics(manifest, change, message):
    mutate(manifest, "task_cases.v1.jsonl", change)
    with pytest.raises(ValueError, match=message):
        load(manifest)


def test_rejects_inexact_unicode_evidence(manifest):
    def change(sources):
        next(bundle for bundle in sources.values() if bundle["evidence"])["evidence"][0]["end"] += 1
    mutate(manifest, "source_bundles/sources.v1.json", change)
    with pytest.raises(ValueError, match="quote|coordinate"):
        load(manifest)


def test_rejects_source_text_hash_mismatch(manifest):
    def change(sources):
        next(bundle for bundle in sources.values() if bundle["documents"])["documents"][0]["text"] += "changed"
    mutate(manifest, "source_bundles/sources.v1.json", change)
    with pytest.raises(ValueError, match="hash"):
        load(manifest)


@pytest.mark.parametrize("change, message", [
    (lambda replay: replay["tools"].pop(), "fixture"),
    (lambda replay: replay["tools"].append(replay["tools"][0]), "duplicate"),
    (lambda replay: replay["tools"][0].update(max_calls=0), "max_calls"),
    (lambda replay: next(iter(replay["task"].values()))["calls"][0].update(context="other"), "context"),
    (lambda replay: replay["tools"][-1]["arguments"]["input"].update(gold_facts=[]), "fixture|orphan"),
])
def test_rejects_invalid_replays(manifest, change, message):
    mutate(manifest, "replays/replays.v1.json", change)
    with pytest.raises(ValueError, match=message):
        load(manifest)


def test_rejects_symlink_escaping_root(manifest):
    original = manifest.parent / "task_cases.v1.jsonl"
    outside = manifest.parent.parent / "outside.jsonl"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    try:
        os.symlink(outside, original)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")
    with pytest.raises(ValueError, match="escape"):
        load(manifest)


def test_cli_returns_machine_readable_success_and_invalid_exit(manifest, capsys):
    from scripts.validate_eval_dataset import main
    assert main([str(manifest)]) == 0
    assert json.loads(capsys.readouterr().out)["task_cases"] == 8
    manifest.write_text("{}", encoding="utf-8")
    assert main([str(manifest)]) == 2
    assert json.loads(capsys.readouterr().out)["valid"] is False
