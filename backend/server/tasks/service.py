"""Async application boundary. Credentials stay in memory, never in task rows."""

import asyncio
import time
from uuid import uuid4
from .models import ResearchTaskRequest
from .task_repository import TaskRepository, TaskConflict


class TaskService:
    def __init__(self, database):
        self.repository = TaskRepository(database)
        self.credentials = {}

    async def call(self, method, *args, **kwargs):
        return await asyncio.to_thread(getattr(self.repository, method), *args, **kwargs)

    async def submit(self, request: ResearchTaskRequest, key=None, *, credentials=None):
        if key is not None and (not key.strip() or len(key)>200):
            raise ValueError('Idempotency-Key 必须为 1 至 200 个字符')
        if request.include_human_feedback:
            raise ValueError('持久人工审核尚未接入，请先关闭人工审核选项')
        if not request.source_policy.network_allowed:
            raise ValueError('当前研究适配器尚不支持强制无网络策略')
        if request.report_source not in request.source_policy.allowed_kinds:
            raise ValueError('资料来源未被来源策略允许')
        explicit = request.budget.model_fields_set
        if (explicit & {'max_tool_calls','max_tokens','max_cost_usd'}):
            raise ValueError('当前仅支持 max_seconds 执行时限，工具、token 和费用硬上限尚未接入')
        if request.mcp_config_refs:
            raise ValueError('尚未配置服务端工具引用解析器')
        if request.mcp_enabled and not (credentials or {}).get('mcp_configs'):
            raise ValueError('启用外部工具需要有效的服务器配置')
        if request.report_type == 'multi_agents' and (request.report_source.value != 'web'
                or request.source_urls or request.document_urls or request.query_domains or request.mcp_enabled):
            raise ValueError('多智能体当前仅支持默认网络来源，其他来源尚未完成适配')
        reference = uuid4().hex if credentials else None
        if reference:
            self.credentials[reference] = (time.monotonic()+3600, credentials)
        try:
            result = await self.call('submit', request.model_dump(mode='json'), key, reference)
        except BaseException:
            self.credentials.pop(reference, None)
            raise
        # A repeated key uses the original persisted credential reference.
        if reference:
            persisted = await self.call('credential_reference', result['research_id'])
            if persisted != reference:
                self.credentials.pop(reference, None)
        return result

    def resolve_credentials(self, reference):
        if not reference:
            return {}
        entry = self.credentials.get(reference)
        if not entry or entry[0] <= time.monotonic():
            self.credentials.pop(reference, None)
            raise LookupError('requires_credentials')
        return entry[1]

    async def wait(self, rid, timeout=30):
        deadline = time.monotonic()+timeout
        while True:
            task = await self.call('get', rid)
            if task['status'] in ('succeeded','failed','cancelled','interrupted'):
                return task
            if time.monotonic() >= deadline:
                return task
            await asyncio.sleep(.1)

    async def legacy_submit(self, data, *, key=None):
        body = {k:data[k] for k in ('task','report_type','report_source','tone','source_urls',
            'document_urls','include_human_feedback','max_search_results','mcp_strategy') if data.get(k) is not None}
        body['query_domains'] = data.get('query_domains') or []
        if body.get('report_source') == 'scholar':
            raise ValueError('学术专用来源尚未接入持久任务接口')
        body['source_policy'] = {'allowed_kinds':[body.get('report_source','web')]}
        if data.get('source_policy') is not None:
            body['source_policy']=data['source_policy']
        if data.get('budget') is not None:
            body['budget']=data['budget']
        body['mcp_enabled'] = bool(data.get('mcp_enabled'))
        strategy=body.get('mcp_strategy','fast')
        body['mcp_strategy']={'optimized':'fast','comprehensive':'deep'}.get(strategy,strategy)
        if data.get('headers') is not None and (not isinstance(data['headers'],dict)
                or any(not isinstance(k,str) or not isinstance(v,str) for k,v in data['headers'].items())):
            raise ValueError('临时请求凭据格式无效')
        if body['mcp_enabled']:
            configs=data.get('mcp_configs')
            if not isinstance(configs,list):
                raise ValueError('工具服务器配置必须为数组')
            for config in configs:
                if not isinstance(config,dict) or not config.get('name') or not (config.get('command') or config.get('connection_url')):
                    raise ValueError('工具服务器配置缺少名称、命令或连接地址')
                if not isinstance(config.get('env',{}),dict) or any(not isinstance(v,str) for v in config.get('env',{}).values()):
                    raise ValueError('工具服务器环境变量必须为文本')
        credentials = {k:data[k] for k in ('headers','mcp_configs') if data.get(k)}
        if not body['mcp_enabled']:
            credentials.pop('mcp_configs',None)
        return await self.submit(ResearchTaskRequest.model_validate(body), key, credentials=credentials or None)

    async def resume(self,rid):
        reference=await self.call('credential_reference',rid)
        try:self.resolve_credentials(reference)
        except LookupError:raise TaskConflict('临时凭据已失效，请新建研究并重新提供凭据。')
        return await self.call('resume',rid)
