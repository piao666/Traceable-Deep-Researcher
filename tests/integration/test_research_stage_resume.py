"""Full-dependency stage integration; model/tool boundaries remain fixed."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from traceable_deep_researcher.agent import TraceableDeepResearcher
from traceable_deep_researcher.runtime.contracts import RunContext
from backend.report_type.basic_report.basic_report import BasicReport


class Store:
    def __init__(self): self.data={}
    async def load(self,context,key): return self.data.get(key)
    async def save(self,context,key,value): self.data[key]=value


def core(context,conductor,writer):
    value=object.__new__(TraceableDeepResearcher)
    value.__dict__.update(query='阶段测试',report_type='research_report',parent_query='',
        run_context=context,agent='固定助手',role='固定角色',log_handler=None,
        research_conductor=SimpleNamespace(conduct_research=conductor),
        report_generator=SimpleNamespace(write_report=writer),image_generator=None,
        context=[],visited_urls=set(),research_sources=[],research_images=[],available_images=[],
        research_costs=0,step_costs={})
    return value


async def test_basic_report_resumes_research_after_writer_failure():
    store=Store()
    conductor=AsyncMock(return_value=['冻结资料'])
    writer=AsyncMock(side_effect=[RuntimeError('injected write failure'),'最终正文'])
    first=object.__new__(BasicReport)
    first.traceable_deep_researcher=core(RunContext('r','a',checkpoint_store=store),conductor,writer)
    with pytest.raises(RuntimeError):
        await first.run()
    second=object.__new__(BasicReport)
    second.traceable_deep_researcher=core(RunContext('r','b',checkpoint_store=store),conductor,writer)
    assert await second.run()=='最终正文'
    conductor.assert_awaited_once()
    assert writer.await_count==2
    assert second.traceable_deep_researcher.context==['冻结资料']


async def test_detailed_resume_reuses_finished_sections():
    from backend.report_type.detailed_report.detailed_report import DetailedReport
    store=Store()
    calls=[]
    fail=True
    def report(attempt):
        value=object.__new__(DetailedReport)
        value.run_context=RunContext('r',attempt,checkpoint_store=store)
        value.traceable_deep_researcher=SimpleNamespace(query='详细报告',report_type='research_report',run_context=value.run_context)
        value.global_context=[];value.global_urls=set();value.global_written_sections=[];value.existing_headers=[];value.subtopics=[]
        async def section(topic):
            calls.append(topic['task'])
            if topic['task']=='第二节' and fail:raise RuntimeError('injected section failure')
            return {'topic':topic,'report':topic['task']+'正文'}
        value._get_subtopic_report=section
        return value
    topics=[{'task':'第一节'},{'task':'第二节'}]
    with pytest.raises(RuntimeError):await report('a')._generate_subtopic_reports(topics)
    fail=False
    results,body=await report('b')._generate_subtopic_reports(topics)
    assert len(results)==2 and body.count('第一节正文')==1
    assert calls==['第一节','第二节','第二节']


async def test_deep_resume_uses_stable_child_paths():
    import asyncio
    from unittest.mock import patch
    from traceable_deep_researcher.skills.deep_research import DeepResearchSkill
    from traceable_deep_researcher.runtime.checkpoints import CheckpointError
    store=Store();created=[];fail=True
    planner=AsyncMock(return_value=[{'query':'q1','researchGoal':'g1'},{'query':'q2','researchGoal':'g2'}])
    def root(attempt):
        return SimpleNamespace(query='深度研究',report_type='deep',run_context=RunContext('r',attempt,checkpoint_store=store),
            cfg=SimpleNamespace(deep_research_breadth=2,deep_research_depth=1,deep_research_concurrency=2,config_path=None),
            websocket=None,tone=None,headers={},visited_urls=set(),mcp_configs=None,mcp_strategy=None,context=[],research_sources=[])
    def nested(**kwargs):
        query=kwargs['query'];created.append(query)
        return SimpleNamespace(conduct_research=AsyncMock(return_value=['资料'+query]),visited_urls=set(),research_sources=[])
    async def process(query,context):
        if query=='q2' and fail:
            await asyncio.sleep(.02)
            raise CheckpointError('injected interruption')
        return {'learnings':[query],'followUpQuestions':[],'citations':{}}
    def skill(attempt):
        value=DeepResearchSkill(root(attempt));value.generate_search_queries=planner;value.process_research_results=process
        return value
    with patch('traceable_deep_researcher.TraceableDeepResearcher',side_effect=nested):
        with pytest.raises(CheckpointError):await skill('a').deep_research('主题',2,1)
        fail=False
        result=await skill('b').deep_research('主题',2,1)
    assert set(result['learnings'])=={'q1','q2'}
    assert created.count('q1')==1 and created.count('q2')==2
    planner.assert_awaited_once()
