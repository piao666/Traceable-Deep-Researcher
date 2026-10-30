import asyncio
import time
from fastapi.testclient import TestClient
from backend.server.tasks.events import handle_task_websocket
from traceable_deep_researcher.runtime.contracts import ResearchResult


def configure(report_app, monkeypatch):
    manager=report_app.manager
    manager.active_connections=[]
    async def connect(ws):
        await ws.accept()
        manager.active_connections.append(ws)
    async def disconnect(ws):
        manager.active_connections.remove(ws)
    async def communication(ws, manager):
        async def no_chat(*args):
            raise AssertionError('chat not expected')
        await handle_task_websocket(ws,manager,chat_handler=no_chat)
    monkeypatch.setattr(manager,'connect',connect,raising=False)
    monkeypatch.setattr(manager,'disconnect',disconnect,raising=False)
    monkeypatch.setattr(report_app,'handle_websocket_communication',communication)


def wait_terminal(client,rid):
    for _ in range(200):
        task=client.get('/api/research/'+rid).json()
        if task['status'] in ('succeeded','failed','cancelled','interrupted'):
            return task
        time.sleep(.02)
    raise AssertionError('task did not finish')


def test_socket_disconnect_does_not_cancel_worker(report_app,monkeypatch):
    configure(report_app,monkeypatch)
    async def runner(request,sink,credentials):
        await asyncio.sleep(.2)
        await sink.send_json({'type':'report','output':'持续执行'})
        return ResearchResult('断线后完成')
    report_app.app.state.research_runner=runner
    with TestClient(report_app.app) as client:
        with client.websocket_connect('/ws') as ws:
            ws.send_text('start {"task":"研究","report_type":"research_report"}')
            created=ws.receive_json()
            rid=created['research_id']
        assert not report_app.manager.active_connections
        assert wait_terminal(client,rid)['status']=='succeeded'
        assert client.get('/api/reports/'+rid).json()['report']['answer']=='断线后完成'


def test_subscribe_replays_in_order_and_explicit_cancel_stops_worker(report_app,monkeypatch):
    configure(report_app,monkeypatch)
    async def runner(*args):
        await asyncio.sleep(60)
        return ResearchResult('不应发布')
    report_app.app.state.research_runner=runner
    with TestClient(report_app.app) as client:
        rid=client.post('/api/research',json={'task':'取消'}).json()['research_id']
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'version':1,'type':'subscribe','research_id':rid,'after_seq':0})
            event=ws.receive_json()
            assert event['research_id']==rid and event['seq']==1
            ws.send_json({'type':'cancel','research_id':rid})
        assert wait_terminal(client,rid)['status']=='cancelled'


def test_legacy_http_wait_returns_full_multi_agent_report(report_app):
    async def runner(*args):
        return ResearchResult('完整多智能体报告，不可截成单个字符')
    report_app.app.state.research_runner=runner
    with TestClient(report_app.app) as client:
        response=client.post('/report/',json={'task':'比较','report_type':'multi_agents',
            'report_source':'web','tone':'Objective','generate_in_background':False})
        assert response.status_code==200
        assert response.json()['report']=='完整多智能体报告，不可截成单个字符'
