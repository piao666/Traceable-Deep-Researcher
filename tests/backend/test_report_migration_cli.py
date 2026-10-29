import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def command(tmp_path, *args):
    return subprocess.run([sys.executable, str(ROOT / "scripts/migrate_report_store.py"),
        "--database-url", f"sqlite:///{(tmp_path / 'cli.db').as_posix()}",
        "--source", str(tmp_path / "reports.json"), *args], cwd=ROOT,
        env={**os.environ, "PYTHONUTF8": "1", "TDR_BLOCK_NETWORK": "1"},
        capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_cli_preview_apply_retry_and_error(tmp_path):
    source = tmp_path / "reports.json"
    source.write_text(json.dumps({"r": {"id": "r", "answer": "中文😀"}}, ensure_ascii=False), encoding="utf-8")
    preview = command(tmp_path)
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)["insert"] == ["r"]
    assert not (tmp_path / "cli.db").exists()
    assert not (tmp_path / "backups").exists()
    applied = command(tmp_path, "--apply")
    assert applied.returncode == 0, applied.stderr
    assert json.loads(applied.stdout)["imported"] == 1
    assert json.loads(command(tmp_path, "--apply").stdout)["skipped"] == 1
    source.write_text('{"r": {"id": "mismatch"}}', encoding="utf-8")
    failed = command(tmp_path, "--apply")
    assert failed.returncode == 2
    assert json.loads(failed.stdout)["errors"][0]["id"] == "r"


def test_cli_missing_source_fails_without_creating_database(tmp_path):
    result = command(tmp_path)
    assert result.returncode == 2 and not (tmp_path / "cli.db").exists()
    assert command(tmp_path, "--init-only").returncode == 0
    assert (tmp_path / "cli.db").exists()


def test_two_importer_processes_serialize_schema_backup_and_records(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    (tmp_path / "reports.json").write_text('{"r":{"id":"r","answer":"body"}}', encoding="utf-8")
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda _: command(tmp_path, "--apply"), range(2)))
    assert all(run.returncode == 0 for run in runs), [run.stderr or run.stdout for run in runs]
    results = [json.loads(run.stdout) for run in runs]
    assert sum(result["imported"] for result in results) == 1
    assert sum(result["skipped"] for result in results) == 1
