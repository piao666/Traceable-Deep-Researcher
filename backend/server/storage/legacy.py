"""Strict, backed-up, transactional import of the retired JSON ReportStore."""

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path

from sqlalchemy import insert, literal_column, select

from .models import legacy_batches, legacy_imports
from ..tasks.repository import ReportRepository, encode, fingerprint, normalize_report


class LegacyMigrationError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LegacyMigrationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise LegacyMigrationError(f"non-finite JSON number: {value}")


@dataclass
class Source:
    path: Path
    raw: bytes
    digest: str
    key: str
    records: dict
    errors: list


def _load(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError) as exc:
        raise LegacyMigrationError(f"Cannot read valid legacy JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LegacyMigrationError("legacy JSON must be an object keyed by report ID")
    records, errors = {}, []
    for rid, value in data.items():
        try:
            records[rid] = normalize_report(rid, value)
        except (ValueError, TypeError, OverflowError) as exc:
            errors.append({"id": rid, "reason": str(exc)})
    return Source(path, raw, sha256(raw).hexdigest(), sha256(os.fsencode(os.path.normcase(str(path)))).hexdigest(), records, errors)


def _classify(source, database, conn=None, *, update_imported=False):
    result = {"valid": not source.errors, "records": len(source.records) + len(source.errors),
              "source_sha256": source.digest, "errors": list(source.errors),
              "insert": [], "update": [], "skip": [], "conflicts": []}
    if conn is None:
        result["insert"] = list(source.records)
        return result
    repo = ReportRepository(database)
    for rid, record in source.records.items():
        receipt = conn.execute(select(legacy_imports.c.record_hash).where(
            legacy_imports.c.source_hash == source.digest, legacy_imports.c.report_id == rid)).first()
        if receipt:
            result["skip"].append(rid)
            continue
        current = repo._get(conn, rid, metadata=False)
        if current is None:
            result["insert"].append(rid)
        elif fingerprint(current) == fingerprint(record):
            result["skip"].append(rid)
        else:
            previous = conn.execute(select(legacy_imports.c.record_hash).where(
                legacy_imports.c.source_key == source.key, legacy_imports.c.report_id == rid)
                .order_by(literal_column("rowid").desc()).limit(1)).scalar()
            if update_imported and previous == fingerprint(current):
                result["update"].append(rid)
            else:
                result["conflicts"].append(rid)
    result["valid"] = result["valid"] and not result["conflicts"]
    return result


def inspect_source(path, database, *, update_imported=False):
    """Preview without creating a DB, upgrading schema, or writing a backup."""
    try:
        source = _load(path)
    except LegacyMigrationError as exc:
        return {"valid": False, "records": 0, "errors": [{"id": None, "reason": str(exc)}],
                "insert": [], "update": [], "skip": [], "conflicts": []}
    if database is None or not database.path.exists():
        return _classify(source, database)
    with database.read() as conn:
        return _classify(source, database, conn, update_imported=update_imported)


def _backup(source, backup_dir):
    folder = Path(backup_dir) if backup_dir else source.path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{source.path.name}.{source.digest}.bak"
    try:
        with path.open("xb") as stream:
            stream.write(source.raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != source.raw:
            raise LegacyMigrationError("Existing backup does not match the source hash")
    manifest_path = Path(str(path) + ".manifest.json")
    manifest = {"source_sha256": source.digest, "bytes": len(source.raw), "records": len(source.records)}
    # A manifest failure prevents the import. A complete backup is retained on all failures.
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise LegacyMigrationError("Existing backup manifest does not match")
    else:
        with manifest_path.open("x", encoding="utf-8") as stream:
            stream.write(encode(manifest) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return str(path)


def migrate_source(path, database, *, backup_dir=None, update_imported=False):
    source = _load(path)
    database.check_schema()
    # Check first so invalid input/conflicts produce no backup or data changes.
    with database.read() as conn:
        preview = _classify(source, database, conn, update_imported=update_imported)
    if not preview["valid"]:
        raise LegacyMigrationError(encode(preview))
    repo = ReportRepository(database)
    with database.write() as conn:
        preview = _classify(source, database, conn, update_imported=update_imported)
        if not preview["valid"]:
            raise LegacyMigrationError(encode(preview))
        # Migration is a maintenance operation: serialize backup creation as well
        # as data writes so two importer processes cannot race on the backup files.
        backup = _backup(source, backup_dir)
        if source.path.read_bytes() != source.raw:
            raise LegacyMigrationError("Legacy source changed during migration; stop all old writers and retry")
        batch_exists = conn.execute(select(legacy_batches.c.source_hash).where(
            legacy_batches.c.source_hash == source.digest)).first()
        if not batch_exists:
            conn.execute(insert(legacy_batches).values(source_hash=source.digest, source_key=source.key,
                         record_count=len(source.records)))
        changed_ids = set(preview["insert"]) | set(preview["update"])
        for rid, record in source.records.items():
            if rid in changed_ids:
                repo._upsert(conn, rid, record, origin="legacy_import")
            receipt = conn.execute(select(legacy_imports.c.report_id).where(
                legacy_imports.c.source_hash == source.digest, legacy_imports.c.report_id == rid)).first()
            if not receipt:
                conn.execute(insert(legacy_imports).values(source_hash=source.digest, report_id=rid,
                             source_key=source.key, record_hash=fingerprint(record)))
        if source.path.read_bytes() != source.raw:
            raise LegacyMigrationError("Legacy source changed before commit; imported records were rolled back")
    return {"source_sha256": source.digest, "imported": len(preview["insert"]) + len(preview["update"]),
            "skipped": len(preview["skip"]), "backup": backup}


def require_imported_source(database, path):
    """Never serve an empty replacement for a forgotten legacy history file."""
    path = Path(path)
    if not path.exists():
        return
    source = _load(path)
    if source.errors:
        raise LegacyMigrationError("Invalid legacy report records; run migration dry-run before starting the API")
    with database.read() as conn:
        batch = conn.execute(select(legacy_batches.c.source_hash).where(
            legacy_batches.c.source_hash == source.digest)).first()
        if not batch:
            raise LegacyMigrationError("Unmigrated or changed legacy history; stop old writers and run scripts/migrate_report_store.py --apply")
