import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from backend.server.storage.database import Database, SchemaError
from backend.server.tasks.task_repository import TaskRepository, TaskConflict, StaleLease


@pytest.fixture
def repository(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'tasks.db').as_posix()}")
    db.migrate()
    yield TaskRepository(db)
    db.dispose()


def test_idempotent_submission_and_conflicting_request(repository):
    request = {"task": "中文研究", "report_type": "deep"}
    a = repository.submit(request, "same")
    assert repository.submit(request, "same")["research_id"] == a["research_id"]
    with pytest.raises(TaskConflict):
        repository.submit({**request, "task": "另一个问题"}, "same")
    assert len(repository.list()) == 1


def test_two_workers_cannot_claim_same_task(repository):
    repository.submit({"task": "问题"})
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda owner: repository.claim(owner, 5), ["one", "two"]))
    assert sum(claim is not None for claim in claims) == 1


def test_expired_worker_cannot_commit_or_renew(repository):
    task = repository.submit({"task": "问题"})
    claim = repository.claim("old", 0.01)
    time.sleep(0.03)
    assert repository.recover_expired() == 1
    assert repository.get(task["research_id"])["status"] == "interrupted"
    repository.resume(task["research_id"])
    newer = repository.claim("new", 5)
    assert newer["fencing_token"] > claim["fencing_token"]
    with pytest.raises(StaleLease):
        repository.complete(claim, {"report_markdown": "过期正文"})
    assert not repository.renew(claim, 5)
    repository.complete(newer, {"report_markdown": "有效正文"})
    assert repository.get(task["research_id"])["result"]["report_markdown"] == "有效正文"


def test_cancellation_wins_against_completion(repository):
    task = repository.submit({"task": "问题"})
    claim = repository.claim("worker", 5)
    repository.cancel(task["research_id"])
    with pytest.raises(StaleLease):
        repository.complete(claim, {"report_markdown": "不能发布"})
    repository.finish_cancel(claim)
    assert repository.get(task["research_id"])["status"] == "cancelled"
    assert repository.database.engine.connect().close() is None


def test_result_report_and_event_are_atomic(repository):
    task = repository.submit({"task": "报告"})
    claim = repository.claim("worker", 5)
    repository.complete(claim, {"report_markdown": "完整中文😀"})
    from backend.server.tasks.repository import ReportRepository
    assert ReportRepository(repository.database).get_report(task["research_id"])["answer"] == "完整中文😀"
    events = repository.events(task["research_id"])
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[-1]["type"] == "task.succeeded"
    assert repository.get(task["research_id"])["last_seq"] == events[-1]["seq"]


def test_resume_rejects_active_and_reopen_retains_queue(repository):
    task = repository.submit({"task": "问题"})
    with pytest.raises(TaskConflict):
        repository.resume(task["research_id"])
    reopened = Database(repository.database.url)
    assert TaskRepository(reopened).get(task["research_id"])["status"] == "queued"
    reopened.dispose()


def test_checkpoint_is_fenced_and_reused_only_with_matching_config(repository):
    task=repository.submit({'task':'检查点'})
    a=repository.claim('one',5)
    value={'schema_version':1,'input_hash':'hash','value':'资料','state':{}}
    repository.save_checkpoint(a,'research_complete','config-one',value)
    repository.fail(a,{'code':'injected'},interrupted=True)
    repository.resume(task['research_id'])
    b=repository.claim('two',5)
    assert repository.load_checkpoint(b,'research_complete','config-one')==value
    with pytest.raises(StaleLease):
        repository.save_checkpoint(a,'research_complete','config-one',value)
    from traceable_deep_researcher.runtime.checkpoints import CheckpointMismatch
    with pytest.raises(CheckpointMismatch):
        repository.load_checkpoint(b,'research_complete','config-two')


def test_expired_cursor_recovers_durable_draft_snapshot(repository,monkeypatch):
    monkeypatch.setenv('TDR_EVENT_RETENTION','3')
    task=repository.submit({'task':'事件保留'})
    claim=repository.claim('worker',5)
    repository.emit(claim,'report.draft_reset',{})
    for word in ('第一段','第二段','第三段','第四段'):
        repository.emit(claim,'report.delta',{'legacy':{'type':'report','output':word}})
    page=repository.event_page(task['research_id'],after_seq=0)
    assert page['resync_required'] is True
    assert page['snapshot']['projection']['draft']=='第一段第二段第三段第四段'
    assert repository.event_page(task['research_id'],after_seq=page['snapshot']['last_seq'])=={'events':[]}


def test_version_one_upgrade_preserves_reports(tmp_path):
    import backend.server.storage.database as module
    import sqlite3
    from hashlib import sha256
    path = tmp_path / 'old.db'
    sql = module.MIGRATION.read_text(encoding='utf-8')
    with sqlite3.connect(path) as conn:
        conn.executescript(sql)
        conn.execute('INSERT INTO schema_migrations(version,checksum) VALUES(1,?)', (sha256(sql.encode()).hexdigest(),))
    db = Database(f"sqlite:///{path.as_posix()}")
    from backend.server.tasks.repository import ReportRepository
    # This version-one report is inserted through the old table layout.
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO reports VALUES('old','{\"id\":\"old\",\"answer\":\"旧正文\"}',1,1,'hash','client','unavailable')")
    with pytest.raises(SchemaError):
        db.check_schema()
    db.migrate()
    assert ReportRepository(db).get_report('old')['answer'] == '旧正文'
    assert db.last_backup and db.last_backup.is_file()
    with sqlite3.connect(db.last_backup) as backup:
        assert backup.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]==1
        assert '旧正文' in backup.execute('SELECT payload_json FROM reports').fetchone()[0]
    db.check_schema()
    db.dispose()


def test_consistent_backup_includes_uncheckpointed_wal(tmp_path):
    import sqlite3
    path=tmp_path/'wal.db'
    source=sqlite3.connect(path)
    source.execute('PRAGMA journal_mode=WAL')
    source.execute('PRAGMA wal_autocheckpoint=0')
    source.execute('CREATE TABLE marker(body TEXT)')
    source.execute("INSERT INTO marker VALUES('WAL中的中文')")
    source.commit()
    # Keep the WAL writer open so closing it cannot checkpoint the file for us.
    assert path.with_name(path.name+'-wal').stat().st_size>0
    db=Database(f"sqlite:///{path.as_posix()}")
    try:
        backup=db.backup()
        with sqlite3.connect(backup) as restored:
            assert restored.execute('SELECT body FROM marker').fetchone()[0]=='WAL中的中文'
    finally:
        source.close();db.dispose()
