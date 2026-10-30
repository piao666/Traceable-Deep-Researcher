import asyncio
from dataclasses import asdict

import pytest
from backend.server.storage.database import Database
from backend.server.tasks.models import ResearchTaskRequest
from backend.server.tasks.service import TaskService
from backend.server.tasks.worker import TaskWorker
from traceable_deep_researcher.runtime.contracts import ResearchResult


@pytest.fixture
def service(tmp_path):
    db=Database(f"sqlite:///{(tmp_path/'worker.db').as_posix()}")
    db.migrate()
    yield TaskService(db)
    db.dispose()


async def test_timeout_cleans_runner_and_does_not_publish(service):
    closed=asyncio.Event()
    async def runner(*args):
        try:
            await asyncio.sleep(60)
        finally:
            closed.set()
    task=await service.submit(ResearchTaskRequest(task='超时',budget={'max_seconds':.03}))
    claim=await service.call('claim','worker',2)
    await TaskWorker(service,runner).execute(claim)
    assert closed.is_set()
    assert (await service.call('get',task['research_id']))['error']['code']=='timeout'
    from backend.server.tasks.repository import ReportRepository
    assert ReportRepository(service.repository.database).get_report(task['research_id']) is None


async def test_missing_ephemeral_credentials_marks_interrupted(service):
    async def forbidden(*args):
        raise AssertionError('runner must not be called without credentials')
    task=await service.submit(ResearchTaskRequest(task='带凭据'),credentials={'headers':{'OPENAI_API_KEY':'offline-secret-canary'}})
    with service.repository.database.engine.connect() as conn:
        from sqlalchemy import text
        stored=conn.execute(text('SELECT request_json,request_hash,credential_ref FROM research_tasks')).all()
    assert 'offline-secret-canary' not in repr(stored)
    service.credentials.clear()
    claim=await service.call('claim','worker',2)
    await TaskWorker(service,forbidden).execute(claim)
    state=await service.call('get',task['research_id'])
    assert state['status']=='interrupted' and state['error']['code']=='requires_credentials'


async def test_cancel_while_runner_returns_acknowledges_cancellation(service):
    task=await service.submit(ResearchTaskRequest(task='完成竞争'))
    claim=await service.call('claim','worker',2)
    async def runner(*args):
        await service.call('cancel',task['research_id'])
        return ResearchResult('不应发布')
    await TaskWorker(service,runner).execute(claim)
    assert (await service.call('get',task['research_id']))['status']=='cancelled'


async def test_shutdown_interrupts_active_attempt_and_keeps_queued_tasks(service):
    started=asyncio.Event()
    closed=asyncio.Event()
    async def runner(*args):
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            closed.set()
    a=await service.submit(ResearchTaskRequest(task='执行中'))
    b=await service.submit(ResearchTaskRequest(task='队列中'))
    worker=TaskWorker(service,runner,shutdown_seconds=.03)
    worker.start()
    await asyncio.wait_for(started.wait(),2)
    await worker.stop()
    assert closed.is_set()
    assert (await service.call('get',a['research_id']))['status']=='interrupted'
    assert (await service.call('get',b['research_id']))['status']=='queued'
