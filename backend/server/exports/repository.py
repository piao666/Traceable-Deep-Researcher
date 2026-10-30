import json
import os
import time
from pathlib import Path
from hashlib import sha256
from uuid import uuid4
from sqlalchemy import text
from ..tasks.task_repository import StaleLease


FORMATS=('pdf','docx','md')


class ExportRepository:
    def __init__(self,database): self.database=database

    @staticmethod
    def enqueue(conn,rid,version=1):
        now=time.time()
        for fmt in FORMATS:
            conn.execute(text('''INSERT OR IGNORE INTO export_jobs
                (job_id,report_id,report_version,format,renderer_version,status,created_at,updated_at)
                VALUES(:id,:rid,:version,:format,:renderer,'queued',:now,:now)'''),
                {'id':uuid4().hex,'rid':rid,'version':version,'format':fmt,
                 'renderer':os.getenv('TDR_EXPORT_RENDERER_VERSION','v1'),'now':now})

    @staticmethod
    def public(job):
        result={k:job[k] for k in ('job_id','report_id','report_version','format','renderer_version','status','error')}
        result['path']=f"api/research/{job['report_id']}/exports/{job['format']}/download?job_id={job['job_id']}" if job['status']=='succeeded' else None
        return result

    def list(self,rid,*,conn=None):
        if conn is None:
            with self.database.read() as connection:
                return self.list(rid,conn=connection)
        jobs=conn.execute(text('SELECT * FROM export_jobs WHERE report_id=:id ORDER BY created_at DESC,job_id'), {'id':rid}).mappings()
        result,seen=[],set()
        for job in jobs:
            key=(job['format'],job['report_version'])
            if key not in seen:
                result.append(self.public(job));seen.add(key)
        return result

    def claim(self,owner,lease_seconds):
        with self.database.write() as conn:
            now=time.time()
            conn.execute(text("UPDATE export_jobs SET status='queued',lease_owner=NULL,lease_until=NULL WHERE status='running' AND lease_until<=:now"), {'now':now})
            job=conn.execute(text("SELECT * FROM export_jobs WHERE status='queued' ORDER BY created_at,job_id LIMIT 1")).mappings().first()
            if not job: return None
            token=job['fencing_token']+1
            conn.execute(text("UPDATE export_jobs SET status='running',lease_owner=:owner,lease_until=:until,fencing_token=:token,updated_at=:now WHERE job_id=:id"),
                         {'owner':owner,'until':now+lease_seconds,'token':token,'now':now,'id':job['job_id']})
            payload=conn.execute(text('SELECT payload_json FROM report_versions WHERE report_id=:id AND version=:version'),
                                 {'id':job['report_id'],'version':job['report_version']}).scalar_one()
            return {**dict(job),'lease_owner':owner,'fencing_token':token,'markdown':json.loads(payload)['answer']}

    def _fence(self,conn,job):
        row=conn.execute(text('SELECT * FROM export_jobs WHERE job_id=:id'),{'id':job['job_id']}).mappings().first()
        if not row or row['status']!='running' or row['fencing_token']!=job['fencing_token'] or row['lease_owner']!=job['lease_owner'] or row['lease_until']<=time.time():
            raise StaleLease('导出执行租约已失效')

    def renew(self,job,seconds):
        with self.database.write() as conn:
            try:self._fence(conn,job)
            except StaleLease:return False
            conn.execute(text('UPDATE export_jobs SET lease_until=:until WHERE job_id=:id'),{'until':time.time()+seconds,'id':job['job_id']})
            return True

    def finish(self,job,*,path=None,artifact_hash=None,error=None):
        if error is None and (not path or not artifact_hash):
            raise ValueError('成功导出必须有文件路径和校验和')
        with self.database.write() as conn:
            self._fence(conn,job)
            status='failed' if error else 'succeeded'
            conn.execute(text('''UPDATE export_jobs SET status=:status,path=:path,artifact_hash=:hash,error=:error,
                lease_owner=NULL,lease_until=NULL,updated_at=:now WHERE job_id=:id'''),
                {'status':status,'path':path,'hash':artifact_hash,'error':error,'now':time.time(),'id':job['job_id']})
            # Use the same task event sequence as research status updates.
            from ..tasks.task_repository import TaskRepository
            TaskRepository(self.database)._event(conn,job['report_id'],'export.'+status,
                {'job_id':job['job_id'],'format':job['format'],'report_version':job['report_version']})

    def retry(self,rid,fmt):
        if fmt not in FORMATS: raise ValueError('不支持的导出格式')
        with self.database.write() as conn:
            row=conn.execute(text('SELECT task_id,current_version FROM reports WHERE report_id=:id'),{'id':rid}).mappings().first()
            if not row or row['task_id']!=rid: raise KeyError(rid)
            self.enqueue(conn,rid,row['current_version'])
            job=conn.execute(text('SELECT * FROM export_jobs WHERE report_id=:id AND report_version=:version AND format=:format AND renderer_version=:renderer'),
                {'id':rid,'version':row['current_version'],'format':fmt,'renderer':os.getenv('TDR_EXPORT_RENDERER_VERSION','v1')}).mappings().one()
            damaged=False
            if job['status']=='succeeded':
                path=Path(job['path']).resolve()
                damaged=Path('outputs').resolve() not in path.parents or not path.is_file() or sha256(path.read_bytes()).hexdigest()!=job['artifact_hash']
            if job['status']=='failed' or damaged:
                conn.execute(text("UPDATE export_jobs SET status='queued',error=NULL,path=NULL,artifact_hash=NULL,updated_at=:now WHERE job_id=:id"),{'now':time.time(),'id':job['job_id']})
                job={**dict(job),'status':'queued','error':None}
            return self.public(job)

    def download(self,rid,fmt,job_id):
        with self.database.read() as conn:
            row=conn.execute(text("SELECT * FROM export_jobs WHERE job_id=:id AND report_id=:rid AND format=:format AND status='succeeded'"),
                             {'id':job_id,'rid':rid,'format':fmt}).mappings().first()
            if not row: raise KeyError(job_id)
            return dict(row)
