import hashlib
import json

import pytest
from sqlalchemy import event, text

from backend.server.storage.database import Database
from backend.server.storage.legacy import LegacyMigrationError, inspect_source, migrate_source, require_imported_source
from backend.server.tasks.repository import ReportRepository


@pytest.fixture
def database(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'tdr.db').as_posix()}")
    db.migrate()
    yield db
    db.dispose()


def source(tmp_path, records=None):
    path = tmp_path / "reports.json"
    records = records if records is not None else {"甲": {"id": "甲", "answer": "中文😀", "timestamp": 12,
        "chatMessages": [{"role": "user", "content": "问题", "extra": 1}]}}
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return path


def test_dry_run_has_no_writes_and_backup_preserves_original(database, tmp_path):
    path = source(tmp_path)
    original = path.read_bytes()
    preview = inspect_source(path, database)
    assert preview["valid"] and preview["records"] == 1 and preview["insert"] == ["甲"]
    assert not list(tmp_path.glob("backups/*"))
    assert ReportRepository(database).list_reports() == []
    result = migrate_source(path, database, backup_dir=tmp_path / "backups")
    assert result["imported"] == 1
    from pathlib import Path
    assert Path(result["backup"]).read_bytes() == original
    assert result["source_sha256"] == hashlib.sha256(original).hexdigest()
    backup_manifest = json.loads(Path(result["backup"] + ".manifest.json").read_text(encoding="utf-8"))
    assert backup_manifest["source_sha256"] == result["source_sha256"]
    saved = ReportRepository(database).get_report("甲")
    assert saved["answer"] == "中文😀"
    assert saved["timestamp"] == 12
    assert saved["chatMessages"][0]["extra"] == 1
    assert saved["origin"] == "legacy_import" and saved["lineage_status"] == "unavailable"
    assert path.read_bytes() == original
    require_imported_source(database, path)
    repeated = migrate_source(path, database, backup_dir=tmp_path / "backups")
    assert repeated["imported"] == 0 and repeated["skipped"] == 1


@pytest.mark.parametrize("raw", ['{', '[]', '{"a":{},"a":{}}', '{"a":{"id":"b"}}',
    '{"a":{"timestamp":true}}', '{"a":{"answer":NaN}}', '{"a":{"chatMessages":{}}}'])
def test_corrupt_source_never_becomes_empty_database(database, tmp_path, raw):
    path = tmp_path / "reports.json"
    path.write_text(raw, encoding="utf-8")
    repo = ReportRepository(database)
    repo.upsert_report("safe", {"id": "safe", "answer": "保留"})
    preview = inspect_source(path, database)
    assert not preview["valid"] and preview["errors"]
    with pytest.raises(LegacyMigrationError):
        migrate_source(path, database, backup_dir=tmp_path / "backups")
    assert repo.get_report("safe")["answer"] == "保留"
    assert not (tmp_path / "backups").exists()


def test_missing_and_empty_source(database, tmp_path):
    with pytest.raises(LegacyMigrationError):
        migrate_source(tmp_path / "absent.json", database)
    path = source(tmp_path, {})
    assert migrate_source(path, database)["imported"] == 0
    require_imported_source(database, path)


def test_id_conflict_is_reported_without_partial_import(database, tmp_path):
    path = source(tmp_path)
    repo = ReportRepository(database)
    repo.upsert_report("甲", {"id": "甲", "answer": "不同正文"})
    preview = inspect_source(path, database)
    assert not preview["valid"] and preview["conflicts"] == ["甲"]
    with pytest.raises(LegacyMigrationError):
        migrate_source(path, database)
    assert repo.get_report("甲")["answer"] == "不同正文"


def test_incremental_import_only_updates_unchanged_imported_target(database, tmp_path):
    path = source(tmp_path)
    migrate_source(path, database)
    records = json.loads(path.read_text(encoding="utf-8"))
    records["甲"]["answer"] = "新版"
    source(tmp_path, records)
    with pytest.raises(LegacyMigrationError):
        require_imported_source(database, path)
    assert not inspect_source(path, database)["valid"]
    assert inspect_source(path, database, update_imported=True)["update"] == ["甲"]
    assert migrate_source(path, database, update_imported=True)["imported"] == 1
    repo = ReportRepository(database)
    assert repo.get_report("甲")["report_version"] == 2
    repo.patch_report("甲", {"answer": "数据库后来修改"}, timestamp=15)
    records["甲"]["answer"] = "另一个旧版修改"
    source(tmp_path, records)
    assert inspect_source(path, database, update_imported=True)["conflicts"] == ["甲"]
    with pytest.raises(LegacyMigrationError):
        migrate_source(path, database, update_imported=True)
    assert repo.get_report("甲")["answer"] == "数据库后来修改"


def test_mid_import_error_rolls_back_every_report_version_chat_and_receipt(database, tmp_path):
    path = source(tmp_path, {"a": {"id": "a", "chatMessages": [{"role": "user", "content": "rollback"}]},
                             "b": {"id": "b"}})
    def fail_second(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO reports") and parameters[0] == "b":
            raise RuntimeError("injected disk failure")
    event.listen(database.engine, "before_cursor_execute", fail_second)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            migrate_source(path, database)
    finally:
        event.remove(database.engine, "before_cursor_execute", fail_second)
    with database.engine.connect() as conn:
        for table in ["reports", "report_versions", "report_chats", "legacy_imports", "legacy_batches"]:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0


def test_startup_refuses_unmigrated_source_and_accepts_receipt(database, tmp_path):
    path = source(tmp_path)
    with pytest.raises(LegacyMigrationError):
        require_imported_source(database, path)
    migrate_source(path, database)
    require_imported_source(database, path)


def test_deleted_import_does_not_resurrect_on_retry(database, tmp_path):
    path = source(tmp_path)
    migrate_source(path, database)
    ReportRepository(database).delete_report("甲")
    assert migrate_source(path, database)["skipped"] == 1
    assert ReportRepository(database).get_report("甲") is None


def test_source_change_after_backup_aborts_before_import(database, tmp_path, monkeypatch):
    from backend.server.storage import legacy
    path = source(tmp_path)
    original_backup = legacy._backup
    def change_source(loaded, folder):
        result = original_backup(loaded, folder)
        path.write_text("{}", encoding="utf-8")
        return result
    monkeypatch.setattr(legacy, "_backup", change_source)
    with pytest.raises(LegacyMigrationError, match="changed"):
        migrate_source(path, database)
    assert ReportRepository(database).list_reports() == []


def test_backup_failure_prevents_all_imports(database, tmp_path, monkeypatch):
    from backend.server.storage import legacy
    path = source(tmp_path)
    def failed(*args):
        raise OSError("backup disk unavailable")
    monkeypatch.setattr(legacy, "_backup", failed)
    with pytest.raises(OSError, match="backup disk"):
        migrate_source(path, database)
    assert ReportRepository(database).list_reports() == []
