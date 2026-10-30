import asyncio
from pathlib import Path
import time
from fastapi.testclient import TestClient
from backend.server.storage.database import Database
from backend.server.report_store import ReportStore
from traceable_deep_researcher.runtime.contracts import ResearchResult


def test_real_socket_sender_cleanup_does_not_own_research(tmp_path,monkeypatch):
    from backend.server import app as module
    db=Database(f"sqlite:///{(tmp_path/'real-ws.db').as_posix()}");db.migrate()
    monkeypatch.setattr(module,'report_store',ReportStore(path=tmp_path/'absent.json',database=db))
    monkeypatch.setattr(module,'manager',module.WebSocketManager())
    async def runner(*args):
        await asyncio.sleep(.2)
        return ResearchResult('真实连接断开后完成')
    async def render(fmt,body,name):
        path=Path('outputs')/f'{name}.{fmt}';path.write_text('fixture',encoding='utf-8');return str(path)
    monkeypatch.setattr(module.app.state,'research_runner',runner,raising=False)
    monkeypatch.setattr(module.app.state,'export_renderer',render,raising=False)
    with TestClient(module.app) as client:
        with client.websocket_connect('/ws') as ws:
            ws.send_text('ping');assert ws.receive_text()=='pong'
            ws.send_text('start {"task":"真实连接清理","report_type":"research_report"}')
            rid=ws.receive_json()['research_id']
        for _ in range(100):
            task=client.get('/api/research/'+rid).json()
            if task['status']=='succeeded':break
            time.sleep(.02)
        assert task['status']=='succeeded'
        assert not module.manager.active_connections
        assert not module.manager.sender_tasks
        assert not module.manager.message_queues
    db.dispose()
