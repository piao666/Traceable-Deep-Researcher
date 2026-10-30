"""JSON-only stage snapshots; no backend, provider or live-object dependency."""

from hashlib import sha256
import json
from uuid import uuid4


class CheckpointError(RuntimeError):
    pass


class CheckpointMismatch(CheckpointError):
    pass


def plain(value):
    if value is None or type(value) in (str,int,float,bool):
        return value
    if isinstance(value, dict):
        return {str(k):plain(v) for k,v in value.items()}
    if isinstance(value, (tuple,list,set)):
        return [plain(v) for v in (sorted(value) if isinstance(value,set) else value)]
    if hasattr(value,'page_content') and hasattr(value,'metadata'):
        return {'page_content':value.page_content,'metadata':plain(value.metadata)}
    raise TypeError('Checkpoint contains a non-JSON runtime object')


def digest(value):
    return sha256(json.dumps(plain(value),ensure_ascii=False,sort_keys=True,
                             separators=(',',':'),allow_nan=False).encode()).hexdigest()


CORE_FIELDS=('context','visited_urls','research_sources','research_images','available_images',
             'research_costs','step_costs','agent','role')
OWNER_FIELDS=('global_context','global_urls','global_written_sections','existing_headers','subtopics')


def core_of(owner):
    return getattr(owner,'traceable_deep_researcher',None) or getattr(owner,'researcher',None) or owner


def snapshot(owner):
    core=core_of(owner)
    return plain({'core':{k:getattr(core,k) for k in CORE_FIELDS if hasattr(core,k)},
                  'owner':{k:getattr(owner,k) for k in OWNER_FIELDS if hasattr(owner,k)}})


def restore(owner, state):
    for obj, fields in ((core_of(owner),state.get('core',{})),(owner,state.get('owner',{}))):
        for key,value in fields.items():
            if key not in CORE_FIELDS+OWNER_FIELDS:
                raise CheckpointMismatch('检查点包含未知状态字段')
            current=getattr(obj,key,None)
            if isinstance(current,set):
                current.update(value)
            else:
                setattr(obj,key,value)


async def checkpoint_call(owner, stage, inputs, action):
    core=core_of(owner)
    context=getattr(owner,'run_context',None) or getattr(core,'run_context',None)
    if context is None or context.checkpoint_store is None:
        return await action()
    scope=digest({'query':getattr(core,'query',''), 'type':getattr(core,'report_type',''),
                  'parent':getattr(core,'parent_query',''), 'scope':context.checkpoint_scope})
    key=f'{type(owner).__name__}:{scope}:{stage}'
    expected=digest(inputs)
    previous=await context.checkpoint_store.load(context,key)
    if previous is not None:
        if (not isinstance(previous,dict) or previous.get('schema_version')!=1
                or previous.get('input_hash')!=expected or 'value' not in previous
                or not isinstance(previous.get('state'),dict)
                or previous.get('checksum')!=digest({k:v for k,v in previous.items() if k!='checksum'})):
            raise CheckpointMismatch('检查点输入或版本不兼容，请新建研究任务')
        restore(owner,previous['state'])
        if context.event_sink:
            await context.event_sink.emit({'type':'stage.restored','payload':{'stage':stage}})
        return previous['value']
    invocation=uuid4().hex
    if context.event_sink:
        await context.event_sink.emit({'type':'invocation.started','payload':{'invocation_id':invocation,'stage':stage}})
    result=await action()
    record={'schema_version':1,'input_hash':expected,'value':plain(result),'state':snapshot(owner),
            'invocation_id':invocation}
    record['checksum']=digest(record)
    # Saving the record and stage.completed is one transaction in durable adapters.
    await context.checkpoint_store.save(context,key,record)
    return result
