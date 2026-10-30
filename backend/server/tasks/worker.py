"""A single in-process worker claims durable tasks; sockets only subscribe."""

import asyncio
from dataclasses import asdict
import logging
import time
from uuid import uuid4

from traceable_deep_researcher.runtime.contracts import ResearchResult, RunContext
from traceable_deep_researcher.runtime.checkpoints import CheckpointMismatch
from .models import ResearchTaskRequest
from .task_repository import StaleLease

logger = logging.getLogger(__name__)


class TaskSink:
    def __init__(self, service, claim):
        self.service, self.claim = service, claim
        self._run_context = None

    @property
    def run_context(self):
        if self._run_context is None:
            from .checkpoints import DurableCheckpoints
            self._run_context=RunContext(self.claim['research_id'],self.claim['current_attempt'],
                event_sink=self,checkpoint_store=DurableCheckpoints(self.service,self.claim))
        return self._run_context

    async def send_json(self, data):
        kind = 'report.delta' if data.get('type') == 'report' else 'legacy.message'
        await self.service.call('emit', self.claim, kind, {'legacy':data})

    async def emit(self, event):
        await self.service.call('emit', self.claim, event['type'], event.get('payload', {}))


class TaskWorker:
    def __init__(self, service, runner, *, lease_seconds=30, poll_seconds=.1, shutdown_seconds=5):
        if lease_seconds <= 0 or poll_seconds <= 0 or shutdown_seconds <= 0:
            raise ValueError('worker 时间设置必须为正数')
        self.service, self.runner = service, runner
        self.lease_seconds, self.poll_seconds, self.shutdown_seconds = lease_seconds, poll_seconds, shutdown_seconds
        self.owner, self.stopping = uuid4().hex, asyncio.Event()
        self.loop_task = None

    def start(self):
        self.loop_task = asyncio.create_task(self.run())

    async def stop(self):
        self.stopping.set()
        if self.loop_task:
            try:
                await asyncio.wait_for(asyncio.shield(self.loop_task), self.shutdown_seconds)
            except TimeoutError:
                self.loop_task.cancel()
                await asyncio.gather(self.loop_task, return_exceptions=True)
        self.service.credentials.clear()

    async def run(self):
        while not self.stopping.is_set():
            try:
                await self.service.call('recover_expired')
                claim = await self.service.call('claim', self.owner, self.lease_seconds)
                if claim:
                    await self.execute(claim)
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('任务 worker 异常，将重新检查持久队列')
            try:
                await asyncio.wait_for(self.stopping.wait(), self.poll_seconds)
            except TimeoutError:
                pass

    async def execute(self, claim):
        running = None
        try:
            try:
                credentials = self.service.resolve_credentials(claim.get('credential_ref'))
            except LookupError:
                await self.service.call('fail', claim, {'code':'requires_credentials',
                    'message':'临时凭据已失效，请重新提交并提供凭据。'}, interrupted=True)
                return
            request = ResearchTaskRequest.model_validate(claim['request'])
            await self.service.call('emit',claim,'report.draft_reset',{'draft_version':claim['fencing_token']})
            running = asyncio.create_task(self.runner(request, TaskSink(self.service, claim), credentials))
            deadline = time.monotonic()+request.budget.max_seconds
            heartbeat = min(self.lease_seconds/3, .25)
            while True:
                done, _ = await asyncio.wait([running], timeout=min(heartbeat, max(.001, deadline-time.monotonic())))
                if done:
                    result = running.result()
                    if not isinstance(result, ResearchResult):
                        raise TypeError('Runner must return ResearchResult')
                    await self.service.call('complete', claim, asdict(result))
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                if not await self.service.call('renew', claim, self.lease_seconds):
                    running.cancel()
                    await asyncio.gather(running, return_exceptions=True)
                    try:
                        await self.service.call('finish_cancel', claim)
                    except StaleLease:
                        pass
                    return
        except asyncio.CancelledError:
            if running:
                running.cancel()
                await asyncio.gather(running, return_exceptions=True)
            try:
                await self.service.call('fail', claim, {'code':'worker_shutdown',
                    'message':'执行进程关闭，任务已中断，远程调用结果可能未知。'}, interrupted=True)
            except StaleLease:
                pass
            raise
        except StaleLease:
            try:
                await self.service.call('finish_cancel', claim)
            except StaleLease:
                pass  # A newer owner won; this attempt cannot publish.
        except Exception as exc:
            if running and not running.done():
                running.cancel()
                await asyncio.gather(running, return_exceptions=True)
            try:
                code='checkpoint_incompatible' if isinstance(exc,CheckpointMismatch) else 'timeout' if isinstance(exc, TimeoutError) else 'runner_failed'
                message='检查点不兼容，请新建研究任务。' if isinstance(exc,CheckpointMismatch) else '研究执行超时。' if isinstance(exc, TimeoutError) else '研究执行失败，请检查服务端日志。'
                await self.service.call('fail', claim, {'code':code,'message':message},interrupted=isinstance(exc,CheckpointMismatch))
            except StaleLease:
                pass
            logger.warning('任务执行未成功：%s (%s)', claim['research_id'], type(exc).__name__)
