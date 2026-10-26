from evals.framework.manifest import content_hash, create_manifest, source_fingerprint


def test_hash_is_stable_for_mapping_order():
    assert content_hash({"b": 1, "a": 2}) == content_hash({"a": 2, "b": 1})


def test_source_fingerprint_detects_untracked_code_but_excludes_results(tmp_path):
    (tmp_path / "evals/results").mkdir(parents=True)
    (tmp_path / "evals/example.py").write_text("a = 1\n", encoding="utf-8")
    before = source_fingerprint(tmp_path)
    (tmp_path / "evals/results/secret.json").write_text('{"private": "report"}', encoding="utf-8")
    assert source_fingerprint(tmp_path) == before
    (tmp_path / "evals/example.py").write_text("a = 2\n", encoding="utf-8")
    assert source_fingerprint(tmp_path) != before


def test_manifest_records_fixture_mode_without_environment_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-appear")
    manifest = create_manifest(tmp_path, dataset_hash="a" * 64, source_hash="b" * 64,
                               config={"suite": "task"}, prompt_inputs={"mode": "fixture"}, seed=0)
    assert manifest["mode"] == "offline"
    assert manifest["evaluation_kind"] == "engineering_replay"
    assert manifest["providers"] == {"model": "fixture-v1", "judge": None}
    assert manifest["dataset_hash"] == "a" * 64
    assert "should-not-appear" not in str(manifest)
    assert len(manifest["dirty_diff_hash"]) == 64


def test_root_dependency_contract_changes_fingerprint(tmp_path):
    config = tmp_path / "pyproject.toml"
    config.write_text('[project]\nversion="0.1.0"\n', encoding="utf-8")
    first = source_fingerprint(tmp_path)
    config.write_text('[project]\nversion="0.2.0"\n', encoding="utf-8")
    assert source_fingerprint(tmp_path) != first
