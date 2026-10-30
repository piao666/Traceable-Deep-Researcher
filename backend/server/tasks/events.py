"""Database-backed subscriptions. Network lifetime never owns research lifetime."""

import asyncio
import json
from pydantic import ValidationError
from .models import SubscribeCommand
from .task_repository import TaskConflict


async def forward_events(websocket, service, rid, after_seq=0, *, legacy=False):
    cursor = after_seq
    try:
        while True:
            page=await service.call('event_page',rid,after_seq=cursor)
            if page.get('resync_required'):
                snapshot=page['snapshot']
                if not legacy:
                    await asyncio.wait_for(websocket.send_json({'version':1,'type':'resync_required',
                        'research_id':rid,'payload':{'snapshot':snapshot}}),5)
                else:
                    await asyncio.wait_for(websocket.send_json({'type':'report_complete',
                        'output':(snapshot['result'] or {}).get('report_markdown') or snapshot['projection']['draft']}),5)
                cursor=snapshot['last_seq']
            events=page['events']
            for event in events:
                if not legacy:
                    await asyncio.wait_for(websocket.send_json(event), 5)
                elif 'legacy' in event['payload']:
                    await asyncio.wait_for(websocket.send_json(event['payload']['legacy']), 5)
                elif event['type'] == 'report.ready':
                    task = await service.call('get', rid)
                    await asyncio.wait_for(websocket.send_json({'type':'report_complete',
                        'output':task['result']['report_markdown']}), 5)
                elif event['type'] == 'task.succeeded':
                    pass  # Legacy path is emitted after independent exports settle.
                elif event['type'] in ('task.failed','task.interrupted','task.cancelled'):
                    await asyncio.wait_for(websocket.send_json({'type':'error','content':event['type'],
                        'output':event['payload'].get('message','研究已停止。')}), 5)
                cursor = event['seq']
            state = await service.call('get', rid)
            if state['status'] in ('succeeded','failed','cancelled','interrupted') and cursor >= state['last_seq']:
                if legacy and state['status']=='succeeded':
                    if any(job['status'] in ('queued','running') for job in state['exports']):
                        await asyncio.sleep(.1)
                        continue
                    paths={job['format']:job['path'] for job in state['exports'] if job['status']=='succeeded'}
                    await asyncio.wait_for(websocket.send_json({'type':'path','output':paths}),5)
                return
            await asyncio.sleep(.1)
    except asyncio.CancelledError:
        raise
    except (KeyError, TimeoutError, RuntimeError):
        return


async def handle_task_websocket(websocket, manager, *, chat_handler):
    service = manager.task_service
    forwarding, chatting = None, None
    rid = None
    try:
        while True:
            data = (await websocket.receive_text()).strip()
            try:
                if data == 'ping':
                    await websocket.send_text('pong')
                    continue
                if data.startswith('start '):
                    if rid and (await service.call('get', rid))['status'] in ('queued','running','cancel_requested'):
                        raise TaskConflict('当前连接已有研究任务，请等待完成或显式取消。')
                    task = await service.legacy_submit(json.loads(data[6:]))
                    rid = task['research_id']
                    await websocket.send_json({'type':'task','content':'created', 'research_id':rid})
                    if forwarding:
                        forwarding.cancel()
                        await asyncio.gather(forwarding, return_exceptions=True)
                    forwarding = asyncio.create_task(forward_events(websocket, service, rid, legacy=True))
                elif data.startswith('chat '):
                    if chatting and not chatting.done():
                        raise TaskConflict('对话请求仍在处理中。')
                    chatting = asyncio.create_task(chat_handler(websocket, data))
                elif data.startswith('{'):
                    command = json.loads(data)
                    if command.get('type') == 'subscribe':
                        parsed = SubscribeCommand.model_validate(command)
                        task = await service.call('get', parsed.research_id)
                        if parsed.after_seq > task['last_seq']:
                            raise ValueError('事件游标超出当前任务范围')
                        rid = parsed.research_id
                        if forwarding:
                            forwarding.cancel()
                            await asyncio.gather(forwarding, return_exceptions=True)
                        forwarding = asyncio.create_task(forward_events(websocket, service, rid, parsed.after_seq))
                    elif command.get('type') == 'cancel':
                        target = command.get('research_id') or rid
                        if not target:
                            raise ValueError('缺少研究任务标识')
                        await service.call('cancel', target)
                    else:
                        raise ValueError('不支持的任务命令')
                else:
                    raise ValueError('不支持的命令；持久人工反馈将在后续批次接入。')
            except (ValueError, KeyError, ValidationError) as exc:
                await websocket.send_json({'type':'error','content':'request_error','output':str(exc)})
    finally:
        for task in (forwarding, chatting):
            if task:
                task.cancel()
        await asyncio.gather(*(task for task in (forwarding, chatting) if task), return_exceptions=True)
