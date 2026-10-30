import asyncio
from fastapi.testclient import TestClient
from traceable_deep_researcher.runtime.contracts import ResearchResult


def test_submit_query_idempotency_and_validation(report_app):
    async def runner(request, sink, credentials):
        return ResearchResult('离线完整报告')
    report_app.app.state.research_runner = runner
    with TestClient(report_app.app) as client:
        body = {'task':'测试研究'}
        first = client.post('/api/research', json=body, headers={'Idempotency-Key':'key'})
        assert first.status_code == 202
        rid = first.json()['research_id']
        assert client.post('/api/research', json=body, headers={'Idempotency-Key':'key'}).json()['research_id'] == rid
        assert client.post('/api/research', json={'task':'不同'}, headers={'Idempotency-Key':'key'}).status_code == 409
        assert client.post('/api/research', json={'task':'x','report_type':'invalid'}).status_code == 422
        assert client.post('/api/research', json={'task':'x','include_human_feedback':True}).status_code == 422
        assert client.post('/api/research', json={'task':'x','source_policy':{'network_allowed':False}}).status_code == 422
        assert client.get('/api/research', params={'limit':0}).status_code == 422
        assert client.get('/api/research/not-found').status_code == 404
        assert client.post('/api/research/'+rid+'/resume').status_code == 409
        assert any(t['research_id'] == rid for t in client.get('/api/research').json()['tasks'])


def test_worker_completes_and_persists_history_without_browser(report_app):
    async def runner(request, sink, credentials):
        await sink.send_json({'type':'report','output':'中文正文'})
        return ResearchResult('中文完整正文', sources=[{'url':'https://example.invalid/source'}])
    report_app.app.state.research_runner = runner
    with TestClient(report_app.app) as client:
        rid = client.post('/api/research', json={'task':'后台研究'}).json()['research_id']
        import time
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            task = client.get('/api/research/'+rid).json()
            if task['status'] == 'succeeded': break
            time.sleep(0.02)
        assert task['status'] == 'succeeded'
        assert task['result']['report_markdown'] == '中文完整正文'
        assert client.get('/api/reports/'+rid).json()['report']['answer'] == '中文完整正文'
        events=client.get('/api/research/'+rid+'/events').json()['events']
        assert any(event['type']=='task.succeeded' for event in events)


def test_cancel_does_not_publish_partial_report(report_app):
    async def runner(request, sink, credentials):
        await asyncio.sleep(60)
        return ResearchResult('不应发布')
    report_app.app.state.research_runner = runner
    with TestClient(report_app.app) as client:
        rid = client.post('/api/research', json={'task':'取消'}).json()['research_id']
        assert client.post('/api/research/'+rid+'/cancel').status_code == 200
        import time
        for _ in range(100):
            task=client.get('/api/research/'+rid).json()
            if task['status']=='cancelled': break
            time.sleep(.02)
        assert task['status']=='cancelled'
        assert client.get('/api/reports/'+rid).status_code == 404
