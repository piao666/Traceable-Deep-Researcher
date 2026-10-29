"""Explicit SQLite setup / JSON import. Without --apply this command is read-only."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import SQLAlchemyError

from backend.server.settings import ServerSettings
from backend.server.storage.database import Database, SchemaError
from backend.server.storage.legacy import inspect_source, migrate_source


def main(argv=None):
    settings = ServerSettings.from_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--source", type=Path, default=settings.legacy_report_path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Back up and import; stop all JSON writers first")
    mode.add_argument("--init-only", action="store_true", help="Initialize/check schema without importing history")
    parser.add_argument("--update-imported", action="store_true", help="Allow same-source deltas only while the DB target still matches its last import")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args(argv)
    database = None
    try:
        database = Database(args.database_url)
        if args.init_only:
            database.migrate()
            result = {"valid": True, "schema_initialized": True, "history_imported": False}
        else:
            # Validate input before any writes; apply then serializes schema setup
            # before querying it, including when another migrator is initializing.
            result = inspect_source(args.source, None if args.apply else database,
                                    update_imported=args.update_imported)
            if result["valid"] and args.apply:
                database.migrate()
                result = {"valid": True, **migrate_source(args.source, database,
                    backup_dir=args.backup_dir, update_imported=args.update_imported)}
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result["valid"] else 2
    except (ValueError, OSError, SchemaError, SQLAlchemyError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    finally:
        if database:
            database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
