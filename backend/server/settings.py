"""Application storage settings, read when the store is constructed."""

import os
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerSettings:
    database_url: str
    legacy_report_path: Path
    worker_lease_seconds: float = 30
    worker_poll_seconds: float = .1
    worker_shutdown_seconds: float = 5
    http_wait_seconds: float = 30
    export_max_seconds: float = 180
    event_retention: int = 20000

    def __post_init__(self):
        for value in (self.worker_lease_seconds,self.worker_poll_seconds,self.worker_shutdown_seconds,self.export_max_seconds):
            if not math.isfinite(value) or value<=0:
                raise ValueError('worker/导出时间设置必须为有限正数')
        if not math.isfinite(self.http_wait_seconds) or self.http_wait_seconds<0 or self.event_retention<0:
            raise ValueError('HTTP 等待时间与事件保留数量必须非负')

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.getenv("TDR_DATABASE_URL", "sqlite:///./data/tdr.db"),
            legacy_report_path=Path(os.getenv("REPORT_STORE_PATH", "data/reports.json")),
            worker_lease_seconds=float(os.getenv('TDR_WORKER_LEASE_SECONDS', '30')),
            worker_poll_seconds=float(os.getenv('TDR_WORKER_POLL_SECONDS', '.1')),
            worker_shutdown_seconds=float(os.getenv('TDR_WORKER_SHUTDOWN_SECONDS', '5')),
            http_wait_seconds=float(os.getenv('TDR_HTTP_WAIT_SECONDS','30')),
            export_max_seconds=float(os.getenv('TDR_EXPORT_MAX_SECONDS','180')),
            event_retention=int(os.getenv('TDR_EVENT_RETENTION','20000')),
        )
