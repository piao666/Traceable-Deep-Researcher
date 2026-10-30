from types import SimpleNamespace
import pytest
from traceable_deep_researcher.runtime.contracts import RunContext
from traceable_deep_researcher.runtime.checkpoints import checkpoint_call, CheckpointMismatch


class MemoryStore:
    def __init__(self): self.data={}
    async def load(self,context,key): return self.data.get(key)
    async def save(self,context,key,value): self.data[key]=value


async def test_resume_reuses_completed_stage_and_restores_context():
    store=MemoryStore()
    context=RunContext('r','a',checkpoint_store=store)
    owner=SimpleNamespace(query='问题',report_type='research_report',run_context=context,
                          context=[],visited_urls=set(),research_costs=0)
    calls=[]
    async def research():
        calls.append(1)
        owner.context=['原文片段']
        owner.visited_urls={'https://example.invalid'}
        owner.research_costs=1.5
        return owner.context
    assert await checkpoint_call(owner,'research_complete',{},research)==['原文片段']
    owner.context=[]
    owner.visited_urls=set()
    owner.run_context=RunContext('r','b',checkpoint_store=store)
    assert await checkpoint_call(owner,'research_complete',{},research)==['原文片段']
    assert calls==[1] and owner.visited_urls=={'https://example.invalid'}
    assert owner.research_costs==1.5


async def test_changed_inputs_or_corrupt_schema_are_not_silently_reused():
    store=MemoryStore()
    owner=SimpleNamespace(query='问题',run_context=RunContext('r','a',checkpoint_store=store))
    async def action(): return '完成'
    await checkpoint_call(owner,'report_written',{'headers':['A']},action)
    with pytest.raises(CheckpointMismatch):
        await checkpoint_call(owner,'report_written',{'headers':['B']},action)
    next(iter(store.data.values()))['schema_version']=999
    with pytest.raises(CheckpointMismatch):
        await checkpoint_call(owner,'report_written',{'headers':['A']},action)


async def test_failed_stage_does_not_create_checkpoint():
    store=MemoryStore()
    owner=SimpleNamespace(query='问题',run_context=RunContext('r','a',checkpoint_store=store))
    async def failure(): raise RuntimeError('provider failure')
    with pytest.raises(RuntimeError):
        await checkpoint_call(owner,'stage',{},failure)
    assert store.data=={}


async def test_modified_checkpoint_payload_is_rejected():
    store=MemoryStore()
    owner=SimpleNamespace(query='检查内容',run_context=RunContext('r','a',checkpoint_store=store))
    async def action(): return '已校验正文'
    await checkpoint_call(owner,'report_written',{},action)
    next(iter(store.data.values()))['value']='被意外改写'
    with pytest.raises(CheckpointMismatch):
        await checkpoint_call(owner,'report_written',{},action)
