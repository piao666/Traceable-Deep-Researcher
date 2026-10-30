from fastapi import APIRouter, Header, HTTPException, Query, Request
from .models import ResearchTaskRequest, TaskStatus
from .task_repository import TaskConflict
from fastapi.responses import FileResponse
from pathlib import Path
from hashlib import sha256
from ..exports.repository import ExportRepository
import asyncio

router = APIRouter(prefix='/api/research', tags=['research tasks'])


def service(request):
    return request.app.state.task_service


async def invoke(request, method, *args, **kwargs):
    try:
        return await service(request).call(method, *args, **kwargs)
    except KeyError:
        raise HTTPException(404, '研究任务不存在')
    except TaskConflict as exc:
        raise HTTPException(409, str(exc))


@router.post('', status_code=202)
async def submit(body: ResearchTaskRequest, request: Request, idempotency_key: str | None = Header(default=None)):
    try:
        return await service(request).submit(body, idempotency_key)
    except TaskConflict as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get('')
async def list_tasks(request: Request, limit: int=Query(50, ge=1, le=200),
                     offset: int=Query(0, ge=0), status: TaskStatus | None=None):
    return {'tasks':await invoke(request, 'list', limit=limit, offset=offset, status=status.value if status else None)}


@router.post('/legacy',status_code=202)
async def legacy_submit(request: Request, idempotency_key: str | None=Header(default=None)):
    try:
        body=await request.json()
        if not isinstance(body,dict):
            raise ValueError('研究请求必须为对象')
        return await service(request).legacy_submit(body,key=idempotency_key)
    except TaskConflict as exc:
        raise HTTPException(409,str(exc))
    except ValueError as exc:
        raise HTTPException(422,str(exc))


@router.get('/{rid}')
async def get_task(rid: str, request: Request):
    return await invoke(request, 'get', rid)


@router.post('/{rid}/cancel')
async def cancel(rid: str, request: Request):
    return await invoke(request, 'cancel', rid)


@router.post('/{rid}/resume', status_code=202)
async def resume(rid: str, request: Request):
    try:return await service(request).resume(rid)
    except KeyError:raise HTTPException(404,'研究任务不存在')
    except TaskConflict as exc:raise HTTPException(409,str(exc))


@router.get('/{rid}/events')
async def events(rid: str, request: Request, after_seq: int=Query(0, ge=0), limit: int=Query(100, ge=1, le=500)):
    return await invoke(request, 'event_page', rid, after_seq=after_seq, limit=limit)


@router.get('/{rid}/exports')
async def exports(rid: str,request: Request):
    task=await invoke(request,'get',rid)
    return {'exports':task['exports']}


@router.post('/{rid}/exports/{fmt}/retry',status_code=202)
async def retry_export(rid: str,fmt: str,request: Request):
    try:
        return await asyncio.to_thread(ExportRepository(service(request).repository.database).retry,rid,fmt)
    except KeyError:raise HTTPException(404,'报告不存在')
    except ValueError as exc:raise HTTPException(422,str(exc))


@router.get('/{rid}/exports/{fmt}/download')
async def download(rid: str,fmt: str,request: Request,job_id: str):
    try:
        job=await asyncio.to_thread(ExportRepository(service(request).repository.database).download,rid,fmt,job_id)
    except KeyError:raise HTTPException(404,'导出文件不存在')
    path=Path(job['path']).resolve()
    if Path('outputs').resolve() not in path.parents or not path.is_file():
        raise HTTPException(404,'导出文件已丢失，请重试导出')
    checksum=await asyncio.to_thread(lambda:sha256(path.read_bytes()).hexdigest())
    if checksum!=job['artifact_hash']:raise HTTPException(409,'导出文件校验失败，请重试导出')
    return FileResponse(path,filename=f"{rid}-v{job['report_version']}.{fmt}",headers={'Cache-Control':'no-store'})
