"""Async compatibility facade; blocking SQLite operations run in worker threads."""

import asyncio
from pathlib import Path

from .settings import ServerSettings
from .storage.database import Database
from .storage.legacy import require_imported_source
from .tasks.repository import ReportRepository


class ReportStore:
    def __init__(self, path: Path | None = None, *, database: Database | None = None):
        settings = ServerSettings.from_env()
        self.database = database or Database(settings.database_url)
        self.legacy_path = path if path is not None else settings.legacy_report_path
        self.repository = ReportRepository(self.database)
        self._initialized = False

    async def initialize(self):
        def check():
            self.database.check_schema()
            require_imported_source(self.database, self.legacy_path)
        await asyncio.to_thread(check)
        self._initialized = True

    async def _call(self, method, *args, **kwargs):
        if not self._initialized:
            await self.initialize()
        return await asyncio.to_thread(method, *args, **kwargs)

    async def list_reports(self, report_ids=None, *, limit=None, offset=0):
        return await self._call(self.repository.list_reports, report_ids, limit=limit, offset=offset)

    async def get_report(self, report_id):
        return await self._call(self.repository.get_report, report_id)

    async def upsert_report(self, report_id, report):
        return await self._call(self.repository.upsert_report, report_id, report)

    async def patch_report(self, report_id, changes, *, timestamp):
        return await self._call(self.repository.patch_report, report_id, changes, timestamp=timestamp)

    async def append_chat_messages(self, report_id, messages, *, timestamp, expected_version=None):
        return await self._call(self.repository.append_chat_messages, report_id, messages,
                                timestamp=timestamp, expected_version=expected_version)

    async def delete_report(self, report_id):
        return await self._call(self.repository.delete_report, report_id)

    async def close(self):
        await asyncio.to_thread(self.database.dispose)
        self._initialized = False
