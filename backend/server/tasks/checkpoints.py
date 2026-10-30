from hashlib import sha256
from pathlib import Path
from traceable_deep_researcher.runtime.checkpoints import digest
from traceable_deep_researcher.runtime.checkpoints import CheckpointMismatch
from .configuration import configuration_snapshot


def code_fingerprint():
    root=Path(__file__).resolve().parents[3]
    files=[]
    for directory in ('traceable_deep_researcher','backend/report_type','multi_agents'):
        files.extend((root/directory).rglob('*.py'))
    result=sha256()
    for path in sorted(files):
        result.update(path.relative_to(root).as_posix().encode())
        result.update(path.read_text(encoding='utf-8').encode())
    return result.hexdigest()


class DurableCheckpoints:
    def __init__(self, service, claim):
        self.service,self.claim=service,claim
        if claim['configuration']!=configuration_snapshot():
            raise CheckpointMismatch('模型或运行配置已变化，请使用新配置创建研究任务。')
        self.base_hash=digest({'request':claim['request'],'configuration':claim['configuration'],
                               'code':code_fingerprint()})

    async def load(self, context, key):
        return await self.service.call('load_checkpoint',self.claim,key,self.base_hash)

    async def save(self, context, key, record):
        await self.service.call('save_checkpoint',self.claim,key,self.base_hash,record)
