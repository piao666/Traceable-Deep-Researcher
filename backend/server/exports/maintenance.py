"""Conservative orphan discovery restricted to application-generated filenames."""

from pathlib import Path
import re
import time
from sqlalchemy import text

FINAL=re.compile(r'^[a-f0-9]{32}-v[0-9]+-([a-f0-9]{32})-[0-9]+\.(pdf|docx|md)$')
TEMP=re.compile(r'^export-([a-f0-9]{32})-[0-9]+-[a-f0-9]{32}\.(pdf|docx|md)$')


def orphan_exports(database,*,root=Path('outputs'),min_age=86400,apply=False):
    if min_age<0:raise ValueError('清理等待时间必须非负')
    root=root.resolve()
    with database.read() as conn:
        rows=conn.execute(text('SELECT job_id,path,status,lease_until FROM export_jobs')).mappings().all()
    references={Path(row['path']).resolve() for row in rows if row['path']}
    active={row['job_id'] for row in rows if row['status']=='running' and (row['lease_until'] or 0)>time.time()}
    candidates=[]
    for directory,pattern in ((root/'exports',FINAL),(root,TEMP)):
        if not directory.is_dir() or directory.is_symlink():continue
        for path in directory.iterdir():
            match=pattern.fullmatch(path.name)
            if not match or path.is_symlink() or not path.is_file():continue
            resolved=path.resolve()
            if root not in resolved.parents or resolved in references or match[1] in active:continue
            if time.time()-path.stat().st_mtime<min_age:continue
            candidates.append(str(path))
            if apply:path.unlink()
    return {'candidates':candidates,'deleted':len(candidates) if apply else 0,'dry_run':not apply}
