"""Lazy provider boundary; importing the queue never loads model clients."""

import os
from dataclasses import asdict
from types import SimpleNamespace
from traceable_deep_researcher.utils.enum import Tone
from traceable_deep_researcher.runtime.contracts import ResearchResult
from traceable_deep_researcher.runtime.checkpoints import checkpoint_call


async def run_research(request, sink, credentials):
    owner=SimpleNamespace(query=request.task,report_type=request.report_type,run_context=sink.run_context)
    async def execute():
        return asdict(await _run_research(request,sink,credentials))
    data=await checkpoint_call(owner,'result_ready',{},execute)
    return ResearchResult(**data)


async def _run_research(request, sink, credentials):
    from ..websocket_manager import run_agent
    return await run_agent(task=request.task, report_type=request.report_type,
        report_source=request.report_source.value, source_urls=request.source_urls,
        document_urls=request.document_urls, tone=Tone[request.tone.value], websocket=sink,
        headers=credentials.get('headers'), query_domains=request.query_domains,
        config_path=os.getenv('CONFIG_PATH','default'), return_result=True,
        mcp_enabled=request.mcp_enabled, mcp_configs=credentials.get('mcp_configs', []),
        mcp_strategy=request.mcp_strategy, max_search_results=request.max_search_results,run_context=sink.run_context)
