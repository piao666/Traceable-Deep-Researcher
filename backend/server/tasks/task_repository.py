"""Short, fenced SQLite transactions for task execution and durable events."""

from datetime import datetime, timezone
import json
import os
import time
from uuid import uuid4

from sqlalchemy import text
from .repository import ReportRepository, encode, fingerprint, normalize_report
from traceable_deep_researcher.runtime.checkpoints import CheckpointMismatch, CheckpointError
from .configuration import configuration_snapshot


class TaskConflict(ValueError):
    pass


class StaleLease(TaskConflict, CheckpointError):
    pass


class TaskRepository:
    def __init__(self, database):
        self.database = database

    def _row(self, conn, rid):
        row = conn.execute(text('SELECT * FROM research_tasks WHERE research_id=:id'), {'id':rid}).mappings().first()
        if row is None:
            raise KeyError(rid)
        return dict(row)

    @staticmethod
    def _decode(row):
        result = dict(row)
        for field in ('request', 'result', 'error', 'configuration', 'projection'):
            value = result.pop(field+'_json', None)
            result[field] = json.loads(value) if value is not None else None
        result.pop('credential_ref', None)
        result['report_id'] = result['research_id'] if result['result'] else None
        result['exports'] = []
        return result

    def _event(self, conn, rid, kind, payload=None):
        row = self._row(conn, rid)
        seq = row['last_seq']+1
        projection=json.loads(row['projection_json'])
        if kind=='report.draft_reset':
            projection={'draft':'','attempt_id':row['current_attempt']}
        legacy=(payload or {}).get('legacy',{})
        if legacy.get('type')=='report' and isinstance(legacy.get('output'),str):
            projection['draft']+=legacy['output']
        elif legacy.get('type')=='report_complete' and isinstance(legacy.get('output'),str):
            projection['draft']=legacy['output']
        conn.execute(text('UPDATE research_tasks SET last_seq=:seq, updated_at=:now WHERE research_id=:id'),
                     {'seq':seq,'now':time.time(),'id':rid})
        conn.execute(text('UPDATE research_tasks SET projection_json=:projection WHERE research_id=:id'),
                     {'projection':encode(projection),'id':rid})
        conn.execute(text('INSERT INTO task_events VALUES(:id,:seq,:attempt,:kind,:payload,:now)'),
                     {'id':rid,'seq':seq,'attempt':row['current_attempt'],'kind':kind,'payload':encode(payload or {}),'now':time.time()})
        retention=int(os.getenv('TDR_EVENT_RETENTION','20000'))
        if retention>0:
            conn.execute(text('DELETE FROM task_events WHERE research_id=:id AND seq<=:floor'),{'id':rid,'floor':seq-retention})

    def submit(self, request, key=None, credential_ref=None):
        digest = fingerprint(request)
        with self.database.write() as conn:
            if key:
                old = conn.execute(text('SELECT * FROM research_tasks WHERE idempotency_key=:key'), {'key':key}).mappings().first()
                if old:
                    if old['request_hash'] != digest:
                        raise TaskConflict('Idempotency-Key 已用于不同的研究请求')
                    return self._decode(old)
            rid, now = uuid4().hex, time.time()
            conn.execute(text('''INSERT INTO research_tasks
                (research_id,request_json,request_hash,idempotency_key,credential_ref,status,configuration_json,created_at,updated_at)
                VALUES(:id,:request,:hash,:key,:credentials,'queued',:config,:now,:now)'''),
                {'id':rid,'request':encode(request),'hash':digest,'key':key,'credentials':credential_ref,'now':now,
                 'config':encode(configuration_snapshot())})
            self._event(conn, rid, 'task.queued')
            return self._decode(self._row(conn, rid))

    def get(self, rid):
        with self.database.read() as conn:
            result=self._decode(self._row(conn, rid))
            from ..exports.repository import ExportRepository
            result['exports']=ExportRepository(self.database).list(rid,conn=conn)
            return result

    def credential_reference(self, rid):
        with self.database.read() as conn:
            return self._row(conn, rid)['credential_ref']

    def list(self, *, limit=50, offset=0, status=None):
        query = 'SELECT * FROM research_tasks'
        if status:
            query += ' WHERE status=:status'
        query += ' ORDER BY created_at DESC, research_id LIMIT :limit OFFSET :offset'
        with self.database.read() as conn:
            from ..exports.repository import ExportRepository
            result=[]
            for row in conn.execute(text(query), {'status':status,'limit':limit,'offset':offset}).mappings():
                item=self._decode(row)
                item['exports']=ExportRepository(self.database).list(item['research_id'],conn=conn)
                result.append(item)
            return result

    def claim(self, owner, lease_seconds):
        with self.database.write() as conn:
            row = conn.execute(text("SELECT * FROM research_tasks WHERE status='queued' ORDER BY created_at,research_id LIMIT 1")).mappings().first()
            if row is None:
                return None
            rid, attempt, token = row['research_id'], uuid4().hex, row['fencing_token']+1
            now = time.time()
            conn.execute(text("""UPDATE research_tasks SET status='running',current_attempt=:attempt,
                fencing_token=:token,lease_owner=:owner,lease_until=:until,error_json=NULL WHERE research_id=:id"""),
                {'attempt':attempt,'token':token,'owner':owner,'until':now+lease_seconds,'id':rid})
            conn.execute(text("INSERT INTO task_attempts VALUES(:attempt,:id,:token,:owner,:now,NULL,'running')"),
                         {'attempt':attempt,'id':rid,'token':token,'owner':owner,'now':now})
            self._event(conn, rid, 'task.started')
            claimed = self._row(conn, rid)
            return {**self._decode(claimed), 'credential_ref':claimed['credential_ref']}

    def _fence(self, conn, claim, *, cancelling=False):
        row = self._row(conn, claim['research_id'])
        statuses = ('running','cancel_requested') if cancelling else ('running',)
        if (row['status'] not in statuses or row['fencing_token'] != claim['fencing_token']
                or row['current_attempt'] != claim['current_attempt'] or row['lease_owner'] != claim['lease_owner']
                or (row['lease_until'] or 0) <= time.time()):
            raise StaleLease('执行租约已失效或任务已取消')
        return row

    def renew(self, claim, lease_seconds):
        with self.database.write() as conn:
            try:
                self._fence(conn, claim)
            except StaleLease:
                return False
            conn.execute(text('UPDATE research_tasks SET lease_until=:until WHERE research_id=:id'),
                         {'until':time.time()+lease_seconds,'id':claim['research_id']})
            return True

    def emit(self, claim, kind, payload):
        with self.database.write() as conn:
            self._fence(conn, claim)
            self._event(conn, claim['research_id'], kind, payload)

    def load_checkpoint(self, claim, key, base_hash):
        with self.database.write() as conn:
            self._fence(conn, claim)
            row=conn.execute(text('SELECT * FROM task_checkpoints WHERE research_id=:id AND stage_key=:key'),
                             {'id':claim['research_id'],'key':key}).mappings().first()
            if row is None:
                return None
            if row['base_hash']!=base_hash:
                raise CheckpointMismatch('检查点的请求、模型配置或代码版本不兼容，请新建研究任务。')
            try:
                return json.loads(row['payload_json'])
            except (ValueError, TypeError) as exc:
                raise CheckpointMismatch('检查点内容损坏，请新建研究任务。') from exc

    def save_checkpoint(self, claim, key, base_hash, record):
        payload=encode(record)
        with self.database.write() as conn:
            self._fence(conn, claim)
            conn.execute(text('''INSERT INTO task_checkpoints VALUES(:id,:key,:hash,:payload,:attempt,:now)
                ON CONFLICT(research_id,stage_key) DO UPDATE SET base_hash=excluded.base_hash,
                payload_json=excluded.payload_json,attempt_id=excluded.attempt_id,created_at=excluded.created_at'''),
                {'id':claim['research_id'],'key':key,'hash':base_hash,'payload':payload,
                 'attempt':claim['current_attempt'],'now':time.time()})
            self._event(conn,claim['research_id'],'stage.completed',{'stage':key,'invocation_id':record.get('invocation_id')})

    def _finish(self, conn, claim, status, error=None):
        conn.execute(text('''UPDATE research_tasks SET status=:status,error_json=:error,
                     lease_owner=NULL,lease_until=NULL WHERE research_id=:id'''),
                     {'status':status,'error':encode(error) if error else None,'id':claim['research_id']})
        conn.execute(text('UPDATE task_attempts SET status=:status,finished_at=:now WHERE attempt_id=:attempt'),
                     {'status':status,'now':time.time(),'attempt':claim['current_attempt']})
        self._event(conn, claim['research_id'], 'task.'+status, error)

    def complete(self, claim, result):
        # Serialize before entering the transaction; reject invalid/partial result types.
        if not isinstance(result.get('report_markdown'), str) or not result['report_markdown'].strip():
            raise ValueError('研究返回了空报告')
        result_json = encode(result)
        with self.database.write() as conn:
            self._fence(conn, claim)
            rid = claim['research_id']
            report = normalize_report(rid, {'id':rid,'question':claim['request']['task'],
                'answer':result['report_markdown'],
                'orderedData':[{'type':'report_complete','content':'','output':result['report_markdown']}], 'chatMessages':[],
                'timestamp':int(time.time()*1000)})
            ReportRepository(self.database)._upsert(conn, rid, report)
            conn.execute(text('UPDATE reports SET task_id=:id WHERE report_id=:id'), {'id':rid})
            conn.execute(text('UPDATE research_tasks SET result_json=:result,review_status=:review WHERE research_id=:id'),
                         {'result':result_json,'review':result.get('review_status','not_requested'),'id':rid})
            self._event(conn, rid, 'report.ready', {'report_id':rid,'version':1})
            from ..exports.repository import ExportRepository
            ExportRepository.enqueue(conn,rid)
            self._finish(conn, claim, 'succeeded')

    def fail(self, claim, error, *, interrupted=False):
        with self.database.write() as conn:
            self._fence(conn, claim)
            self._finish(conn, claim, 'interrupted' if interrupted else 'failed', error)

    def cancel(self, rid):
        with self.database.write() as conn:
            row = self._row(conn, rid)
            if row['status'] in ('succeeded','failed','cancelled','interrupted'):
                return self._decode(row)
            status = 'cancel_requested' if row['status'] == 'running' else 'cancelled'
            conn.execute(text('UPDATE research_tasks SET status=:status WHERE research_id=:id'), {'status':status,'id':rid})
            self._event(conn, rid, 'task.'+status)
            return self._decode(self._row(conn, rid))

    def finish_cancel(self, claim):
        with self.database.write() as conn:
            self._fence(conn, claim, cancelling=True)
            self._finish(conn, claim, 'cancelled')

    def resume(self, rid):
        with self.database.write() as conn:
            row = self._row(conn, rid)
            if row['status'] not in ('failed','interrupted'):
                raise TaskConflict('仅中断或失败的研究可以重新执行')
            conn.execute(text("UPDATE research_tasks SET status='queued',error_json=NULL WHERE research_id=:id"), {'id':rid})
            self._event(conn, rid, 'task.queued', {'restart':True,'warning':'将复用兼容的已完成阶段；未完成阶段可能重新调用模型或工具并重复计费。'})
            return self._decode(self._row(conn, rid))

    def recover_expired(self):
        with self.database.write() as conn:
            expired = conn.execute(text("SELECT * FROM research_tasks WHERE status IN ('running','cancel_requested') AND lease_until<=:now"), {'now':time.time()}).mappings().all()
            for row in expired:
                self._finish(conn, row, 'cancelled' if row['status']=='cancel_requested' else 'interrupted',
                             {'code':'lease_expired','message':'执行进程失去租约，需要显式恢复；远程调用结果可能未知。'})
            return len(expired)

    def events(self, rid, *, after_seq=0, limit=100):
        with self.database.read() as conn:
            self._row(conn, rid)
            return self._events(conn,rid,after_seq,limit)

    def _events(self,conn,rid,after_seq,limit):
        rows = conn.execute(text('SELECT * FROM task_events WHERE research_id=:id AND seq>:seq ORDER BY seq LIMIT :limit'),
                            {'id':rid,'seq':after_seq,'limit':limit}).mappings()
        return [{'version':1,'research_id':rid,'attempt_id':r['attempt_id'],'seq':r['seq'],
            'type':r['event_type'],'payload':json.loads(r['payload_json']),
            'created_at':datetime.fromtimestamp(r['created_at'], timezone.utc).isoformat()} for r in rows]

    def event_page(self,rid,*,after_seq=0,limit=100):
        with self.database.read() as conn:
            row=self._row(conn,rid)
            first=conn.execute(text('SELECT MIN(seq) FROM task_events WHERE research_id=:id'),{'id':rid}).scalar()
            if after_seq>row['last_seq']:
                raise TaskConflict('事件游标超出任务范围')
            if first and after_seq<first-1:
                snapshot=self._decode(row)
                from ..exports.repository import ExportRepository
                snapshot['exports']=ExportRepository(self.database).list(rid,conn=conn)
                return {'resync_required':True,'snapshot':snapshot,'events':[]}
            return {'events':self._events(conn,rid,after_seq,limit)}
