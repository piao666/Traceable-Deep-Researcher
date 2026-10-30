import asyncio
from hashlib import sha256
import os
from pathlib import Path
from uuid import uuid4

from .repository import ExportRepository
from ..tasks.task_repository import StaleLease


async def render_document(fmt,markdown,basename):
    def render():
        from backend.utils import write_md_to_pdf,write_md_to_word,write_text_to_md
        function={'pdf':write_md_to_pdf,'docx':write_md_to_word,'md':write_text_to_md}[fmt]
        return asyncio.run(function(markdown,basename))
    return await asyncio.to_thread(render)


class ExportWorker:
    def __init__(self,database,renderer=render_document):
        self.repository=ExportRepository(database)
        self.renderer=renderer
        self.stopping=asyncio.Event()
        self.owner=uuid4().hex
        self.loop_task=None

    async def call(self,method,*args,**kwargs):
        return await asyncio.to_thread(getattr(self.repository,method),*args,**kwargs)

    def start(self): self.loop_task=asyncio.create_task(self.run())

    async def stop(self):
        self.stopping.set()
        if self.loop_task:
            self.loop_task.cancel()
            await asyncio.gather(self.loop_task,return_exceptions=True)

    async def run(self):
        while not self.stopping.is_set():
            try:
                job=await self.call('claim',self.owner,120)
                if job: await self.execute(job)
                else: await asyncio.sleep(.15)
            except asyncio.CancelledError: raise
            except Exception:
                await asyncio.sleep(.5)

    async def execute(self,job):
        running=None
        try:
            basename=f"export-{job['job_id']}-{job['fencing_token']}-{uuid4().hex}"
            running=asyncio.create_task(self.renderer(job['format'],job['markdown'],basename))
            deadline=asyncio.get_running_loop().time()+float(os.getenv('TDR_EXPORT_MAX_SECONDS','180'))
            while not running.done():
                await asyncio.wait([running],timeout=.5)
                if asyncio.get_running_loop().time()>deadline: raise TimeoutError()
                if not await self.call('renew',job,120): raise StaleLease('导出租约已失效')
            temporary=Path(running.result()).resolve()
            root=Path('outputs').resolve()
            if root not in temporary.parents or not temporary.is_file():
                raise ValueError('导出器未生成有效文件')
            managed=root/'exports'
            managed.mkdir(parents=True,exist_ok=True)
            target=managed/f"{job['report_id']}-v{job['report_version']}-{job['job_id']}-{job['fencing_token']}.{job['format']}"
            await asyncio.to_thread(os.replace,temporary,target)
            checksum=await asyncio.to_thread(lambda:sha256(target.read_bytes()).hexdigest())
            await self.call('finish',job,path=target.relative_to(Path.cwd()).as_posix(),artifact_hash=checksum)
        except asyncio.CancelledError:
            if running:running.cancel()
            try:await self.call('finish',job,error='导出进程已停止，可单独重试。')
            except StaleLease:pass
            raise
        except StaleLease:
            if running:running.cancel()
        except Exception:
            if running:running.cancel()
            try:await self.call('finish',job,error='文件生成失败，可单独重试；研究正文已保存。')
            except StaleLease:pass
        finally:
            if running:await asyncio.gather(running,return_exceptions=True)
