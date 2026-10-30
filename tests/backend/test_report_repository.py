import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from backend.server.report_store import ReportStore
from backend.server.storage.database import Database, SchemaError
from backend.server.tasks.repository import ReportRepository


@pytest.fixture
def database(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'tdr.db').as_posix()}")
    db.migrate()
    yield db
    db.dispose()


def report(rid="报告-😀", timestamp=1):
    return {"id": rid, "question": "问题", "answer": "中文😀正文", "orderedData": [],
            "chatMessages": [{"role": "user", "content": "原消息"}],
            "timestamp": timestamp, "extension": {"preserved": True}}


def test_schema_is_explicit_and_versions_are_checked(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    with pytest.raises(SchemaError):
        db.check_schema()
    assert not (tmp_path / "fresh.db").exists()
    db.migrate()
    db.migrate()
    db.check_schema()
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE schema_migrations SET version=999 WHERE version=(SELECT MAX(version) FROM schema_migrations)"))
    with pytest.raises(SchemaError):
        db.check_schema()
    with pytest.raises(SchemaError):
        db.migrate()
    db.dispose()


def test_sqlite_pragmas_and_reopen(database):
    with database.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() >= 5000
    ReportRepository(database).upsert_report("报告-😀", report())
    url = database.url
    database.dispose()
    reopened = Database(url)
    assert ReportRepository(reopened).get_report("报告-😀")["answer"] == "中文😀正文"
    reopened.dispose()


def test_crud_pagination_and_immutable_content_versions(database):
    repo = ReportRepository(database)
    for rid in ["a", "b", "c"]:
        repo.upsert_report(rid, report(rid, 2 if rid != "c" else 3))
    assert [r["id"] for r in repo.list_reports(limit=2)] == ["c", "a"]
    assert [r["id"] for r in repo.list_reports(limit=2, offset=2)] == ["b"]
    assert [r["id"] for r in repo.list_reports(["b", "missing"])] == ["b"]
    assert repo.list_reports([]) == []
    repo.patch_report("a", {"answer": "第二版"}, timestamp=5)
    repo.append_chat_messages("a", [{"role": "assistant", "content": "追加"}], timestamp=6)
    current = repo.get_report("a")
    assert current["report_version"] == 2
    assert current["extension"] == {"preserved": True}
    assert len(current["chatMessages"]) == 2
    repo.upsert_report("a", {**current, "timestamp": 1})
    assert repo.get_report("a")["timestamp"] == 6
    with database.engine.connect() as conn:
        versions = conn.execute(text("SELECT version, payload_json FROM report_versions WHERE report_id='a' ORDER BY version")).all()
        assert len(versions) == 2
        assert "中文" in versions[0].payload_json
        assert "第二版" in versions[1].payload_json
        chat_versions = conn.execute(text("SELECT report_version FROM report_chats WHERE report_id='a' ORDER BY position")).scalars().all()
        assert chat_versions == [1, 2]
    with pytest.raises(Exception, match="immutable"):
        with database.engine.begin() as conn:
            conn.execute(text("UPDATE report_versions SET payload_json='{}' WHERE report_id='a' AND version=1"))
    assert repo.delete_report("a")
    assert not repo.delete_report("a")
    assert repo.get_report("a") is None
    with database.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM report_chats WHERE report_id='a'")).scalar() == 0


def test_concurrent_writes_and_atomic_chat_updates(database):
    repo = ReportRepository(database)
    repo.upsert_report("shared", report("shared"))
    def write(i):
        other = ReportRepository(database)
        other.upsert_report(str(i), report(str(i)))
        other.patch_report("shared", {f"field_{i}": i}, timestamp=i + 10)
        other.append_chat_messages("shared", [{"role": "user", "content": str(i)}], timestamp=i + 10)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(write, range(18)))
    saved = repo.get_report("shared")
    assert all(saved[f"field_{i}"] == i for i in range(18))
    assert len(saved["chatMessages"]) == 19
    assert len(repo.list_reports()) == 19


def test_two_schema_migrators_serialize(tmp_path):
    url = f"sqlite:///{(tmp_path / 'concurrent.db').as_posix()}"
    def migrate(_):
        db = Database(url)
        try:
            db.migrate()
        finally:
            db.dispose()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(migrate, range(2)))
    db = Database(url)
    db.check_schema()
    db.dispose()


def test_report_store_facade_does_not_block_event_loop(database):
    import threading
    async def run():
        store = ReportStore(database=database)
        loop_thread = threading.get_ident()
        original_get = store.repository.get_report
        def checked_get(rid):
            assert threading.get_ident() != loop_thread
            return original_get(rid)
        store.repository.get_report = checked_get
        await store.initialize()
        await store.upsert_report("r", report("r"))
        assert (await store.list_reports(limit=1))[0]["id"] == "r"
        assert await store.patch_report("r", {"question": "更新"}, timestamp=2)
        assert await store.append_chat_messages("r", [{"role": "assistant", "content": "回复"}], timestamp=3)
        assert (await store.get_report("r"))["question"] == "更新"
        assert await store.delete_report("r")
    asyncio.run(run())


def test_schema_failure_rolls_back_ddl(tmp_path, monkeypatch):
    import backend.server.storage.database as module
    migration = tmp_path / "bad.sql"
    migration.write_text("CREATE TABLE accidental(id INTEGER);\nINVALID SQL;\n", encoding="utf-8")
    monkeypatch.setattr(module, "MIGRATION", migration)
    db = Database(f"sqlite:///{(tmp_path / 'bad.db').as_posix()}")
    from sqlalchemy.exc import SQLAlchemyError
    with pytest.raises(SQLAlchemyError):
        db.migrate()
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).all() == []
    db.dispose()


@pytest.mark.parametrize("limit,offset", [(0, 0), (-1, 0), (1, -1), (True, 0)])
def test_invalid_pagination(database, limit, offset):
    with pytest.raises(ValueError):
        ReportRepository(database).list_reports(limit=limit, offset=offset)
