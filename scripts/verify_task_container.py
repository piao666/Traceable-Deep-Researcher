"""Isolated task/worker smoke: real Linux API and storage, fixed provider boundary.

No real environment file or user data is mounted. No paid provider is called.
The fixed runner classes are installed only in this test process, never via a
production environment flag. Cleanup uses the A1 helper's ownership checks.
"""

import argparse
import json
from pathlib import Path
import time

from verify_a1_container import Smoke, docker, DATA, ENVIRONMENT


SERVER = r'''
import asyncio
import uvicorn
from backend.server import app as api
from server import websocket_manager as runners
class FixedReport:
    def __init__(self, **kwargs):
        self.query=kwargs['query']
        self.websocket=kwargs['websocket']
        self.traceable_deep_researcher=self
    async def run(self):
        if self.query=='hold':
            await asyncio.sleep(60)
        await self.websocket.send_json({'type':'report','output':'中文报告片段'})
        return '完整中文研究报告😀，不能截断'
    def get_source_urls(self): return ['https://example.invalid/source']
    def get_costs(self): return 0
async def fixed_multi(**kwargs):
    assert kwargs['task_overrides']['include_human_feedback'] is False
    return {'report':'完整多智能体报告😀'}
runners.BasicReport=runners.DetailedReport=FixedReport
runners.run_multi_agent_task=fixed_multi
uvicorn.run(api.app,host='0.0.0.0',port=8000)
'''


class TaskSmoke(Smoke):
    def start(self, volume, suffix):
        name=self.prefix+'-'+suffix
        self.containers.add(name)
        docker('run','-d','--name',name,'--label','tdr.validation.run='+self.prefix,
               '--network','none',*ENVIRONMENT,'-e','TDR_WORKER_LEASE_SECONDS=1',
               '--mount',f'type=volume,src={volume},dst={DATA}',self.image,'python','-c',SERVER)
        return name

    def state(self, container, rid, expected, timeout=20):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            reply=self.request(container,'/api/research/'+rid)
            if reply['status']==200 and reply['body']['status'] in expected:
                return reply['body']
            time.sleep(.05)
        raise AssertionError(('task state timeout',reply))

    def run(self):
        volume=self.volume('tasks')
        self.migrate(volume,'--init-only')
        server=self.start(volume,'first')
        self.ready(server)
        self.passed('real Linux API starts with explicit schema and non-root data volume')
        for kind in ('research_report','detailed_report','deep','multi_agents'):
            response=self.request(server,'/api/research','POST',{'task':'fixture','report_type':kind})
            assert response['status']==202,response
            rid=response['body']['research_id']
            task=self.state(server,rid,{'succeeded','failed'})
            assert task['status']=='succeeded',task
            expected='完整多智能体报告😀' if kind=='multi_agents' else '完整中文研究报告😀，不能截断'
            assert task['result']['report_markdown']==expected,task
            history=self.request(server,'/api/reports/'+rid)
            assert history['body']['report']['answer']==expected,history
            events=self.request(server,'/api/research/'+rid+'/events')['body']['events']
            assert [e['seq'] for e in events]==list(range(1,len(events)+1))
            self.passed(kind+' normalized result, history and durable event order')
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            jobs=self.request(server,'/api/research/'+rid+'/exports')['body']['exports']
            if all(job['status'] in ('succeeded','failed') for job in jobs):break
            time.sleep(.2)
        assert len(jobs)==3 and all(job['status']=='succeeded' for job in jobs),jobs
        native = r'''
import io,json,sys,urllib.request,zipfile
jobs=json.load(sys.stdin)
for job in jobs:
    body=urllib.request.urlopen('http://127.0.0.1:8000/'+job['path']).read()
    if job['format']=='pdf':assert body.startswith(b'%PDF')
    elif job['format']=='docx':
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            assert '完整多智能体报告' in archive.read('word/document.xml').decode()
    else:assert '完整多智能体报告' in body.decode()
print('native exports valid')
'''
        docker('exec','-i',server,'python','-c',native,stdin=json.dumps(jobs))
        self.passed('native Linux PDF DOCX and Unicode Markdown downloads through owned jobs')
        running=self.request(server,'/api/research','POST',{'task':'hold'})['body']['research_id']
        self.state(server,running,{'running'})
        queued=self.request(server,'/api/research','POST',{'task':'queued fixture'})['body']['research_id']
        docker('kill','--signal','KILL',server)
        self.remove_owned_container(server)
        time.sleep(1.2)
        replacement=self.start(volume,'replacement')
        self.ready(replacement)
        interrupted=self.state(replacement,running,{'interrupted'})
        assert interrupted['error']['code']=='lease_expired'
        assert self.state(replacement,queued,{'succeeded','failed'})['status']=='succeeded'
        self.passed('process replacement retains queue and marks unknown running outcome interrupted')
        resumed=self.request(replacement,'/api/research/'+running+'/resume','POST')
        assert resumed['status']==202,resumed
        latest=self.state(replacement,running,{'running'})
        assert latest['fencing_token']>interrupted['fencing_token']
        self.request(replacement,'/api/research/'+running+'/cancel','POST')
        self.state(replacement,running,{'cancelled'})
        assert self.request(replacement,'/api/reports/'+running)['status']==404
        self.passed('explicit restart creates new attempt and cancellation prevents report publication')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='tdr-task-validation:20261030')
    parser.add_argument('--out',type=Path,default=Path('evals/results/task-container-20261030/summary.json'))
    args=parser.parse_args()
    smoke=TaskSmoke(args.image)
    started=time.monotonic()
    error=None
    try:
        smoke.run()
    except Exception as exc:
        error=str(exc)
    finally:
        failures=smoke.cleanup()
    result={'checks':smoke.checks,'error':error,'cleanup_errors':failures,
            'seconds':round(time.monotonic()-started,2),'provider_calls':0}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    return 1 if error or failures else 0


if __name__=='__main__':
    raise SystemExit(main())
