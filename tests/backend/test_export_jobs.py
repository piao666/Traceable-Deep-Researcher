import pytest
from backend.server.storage.database import Database
from backend.server.tasks.task_repository import TaskRepository
from backend.server.exports.repository import ExportRepository


@pytest.fixture
def exports(tmp_path):
    db=Database(f"sqlite:///{(tmp_path/'export.db').as_posix()}")
    db.migrate()
    tasks=TaskRepository(db)
    task=tasks.submit({'task':'导出'})
    claim=tasks.claim('research',5)
    tasks.complete(claim,{'report_markdown':'# 冻结正文'})
    yield ExportRepository(db),tasks,task['research_id']
    db.dispose()


def test_export_failures_do_not_change_task_success(exports):
    repo,tasks,rid=exports
    jobs=repo.list(rid)
    assert {j['format'] for j in jobs}=={'pdf','docx','md'}
    claim=repo.claim('exporter',5)
    assert claim['markdown']=='# 冻结正文'
    repo.finish(claim,error='导出失败')
    assert tasks.get(rid)['status']=='succeeded'
    assert any(j['status']=='failed' for j in repo.list(rid))


def test_export_retry_is_idempotent(exports):
    repo,tasks,rid=exports
    claim=repo.claim('exporter',5)
    repo.finish(claim,error='注入失败')
    first=repo.retry(rid,claim['format'])
    second=repo.retry(rid,claim['format'])
    assert first['job_id']==second['job_id'] and second['status']=='queued'
    assert len(repo.list(rid))==3


def test_stale_client_cannot_overwrite_managed_report_or_erase_chat(exports):
    repo,tasks,rid=exports
    from backend.server.tasks.repository import ReportRepository,ReportVersionConflict
    reports=ReportRepository(repo.database)
    original=reports.get_report(rid)
    assert original['origin']=='task'
    reports.append_chat_messages(rid,[{'role':'user','content':'新消息'}],timestamp=2)
    reports.upsert_report(rid,original)
    assert reports.get_report(rid)['chatMessages'][0]['content']=='新消息'
    with pytest.raises(ReportVersionConflict):
        reports.upsert_report(rid,{**original,'answer':'过期缓存正文'})
    assert reports.get_report(rid)['answer']=='# 冻结正文'


def test_expired_export_lease_cannot_publish(exports):
    repo,tasks,rid=exports
    import time
    from backend.server.tasks.task_repository import StaleLease
    claim=repo.claim('old',.01)
    time.sleep(.03)
    newer=repo.claim('new',5)
    assert newer['job_id']==claim['job_id']
    with pytest.raises(StaleLease):
        repo.finish(claim,error='旧执行结果')


def test_frozen_export_uses_version_payload(exports):
    repo,tasks,rid=exports
    claim=repo.claim('worker',5)
    assert claim['report_version']==1 and claim['markdown']=='# 冻结正文'


@pytest.mark.asyncio
async def test_worker_isolates_one_renderer_failure(exports,tmp_path,monkeypatch):
    from backend.server.exports.worker import ExportWorker
    from pathlib import Path
    monkeypatch.chdir(tmp_path)
    Path('outputs').mkdir()
    repo,tasks,rid=exports
    calls=[]
    async def render(fmt,body,name):
        calls.append(fmt)
        if fmt=='pdf':raise RuntimeError('固定渲染失败')
        path=Path('outputs')/f'{name}.{fmt}'
        path.write_text(body,encoding='utf-8')
        return str(path)
    worker=ExportWorker(repo.database,render)
    for _ in range(3):
        await worker.execute(repo.claim('test',10))
    states={job['format']:job['status'] for job in repo.list(rid)}
    assert states=={'pdf':'failed','docx':'succeeded','md':'succeeded'}
    assert tasks.get(rid)['status']=='succeeded'
    repo.retry(rid,'pdf')
    assert repo.claim('retry',10)['format']=='pdf'
    assert len(calls)==3


def test_download_ownership_checksum_and_retry(report_app):
    from fastapi.testclient import TestClient
    from hashlib import sha256
    from pathlib import Path
    db=report_app.report_store.database
    tasks=TaskRepository(db)
    rid=tasks.submit({'task':'文件归属'})['research_id']
    tasks.complete(tasks.claim('test',10),{'report_markdown':'# 中文'})
    repo=ExportRepository(db)
    job=repo.claim('export',10)
    path=Path('outputs')/'exports'/'fixture.md'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('# 中文',encoding='utf-8')
    repo.finish(job,path=str(path),artifact_hash=sha256(path.read_bytes()).hexdigest())
    with TestClient(report_app.app) as client:
        route=f"/api/research/{rid}/exports/{job['format']}/download?job_id={job['job_id']}"
        assert client.get(route).status_code==200
        assert client.get(route.replace(rid,'other')).status_code==404
        path.write_text('损坏',encoding='utf-8')
        assert client.get(route).status_code==409
        assert repo.retry(rid,job['format'])['status']=='queued'


def test_orphan_cleanup_preserves_references_active_jobs_and_user_files(exports,tmp_path):
    import os
    from backend.server.exports.maintenance import orphan_exports
    from uuid import uuid4
    repo,tasks,rid=exports
    root=tmp_path/'outputs';managed=root/'exports';managed.mkdir(parents=True)
    claim=repo.claim('active',10)
    active=managed/f"{rid}-v1-{claim['job_id']}-1.md"
    orphan=managed/f'{rid}-v1-{uuid4().hex}-1.md'
    user=managed/'my-report.md'
    for path in (active,orphan,user):
        path.write_text('固定文件',encoding='utf-8');os.utime(path,(1,1))
    found=orphan_exports(repo.database,root=root)
    assert found['candidates']==[str(orphan)] and found['deleted']==0
    assert orphan.exists()
    removed=orphan_exports(repo.database,root=root,apply=True)
    assert removed['deleted']==1 and active.exists() and user.exists()
