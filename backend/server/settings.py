"""Application storage settings, read when the store is constructed."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerSettings:
    database_url: str
    legacy_report_path: Path

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.getenv("TDR_DATABASE_URL", "sqlite:///./data/tdr.db"),
            legacy_report_path=Path(os.getenv("REPORT_STORE_PATH", "data/reports.json")),
        )
