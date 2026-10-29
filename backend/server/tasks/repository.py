"""Transactional report persistence, shared by the API and legacy importer."""

from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import delete, insert, select, update

from ..storage.models import reports, report_versions, report_chats


STORAGE_FIELDS = {"origin", "lineage_status", "report_version"}


class ReportVersionConflict(RuntimeError):
    """A chat reply was generated against a report version that has changed."""


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return sha256(encode(value).encode("utf-8")).hexdigest()


def normalize_report(report_id, value):
    if not isinstance(report_id, str) or not report_id.strip():
        raise ValueError("report ID must be a nonempty string")
    if not isinstance(value, dict) or value.get("id", report_id) != report_id:
        raise ValueError("report object ID must match its storage key")
    record = {k: v for k, v in value.items() if k not in STORAGE_FIELDS}
    record["id"] = report_id
    if "timestamp" in record and (type(record["timestamp"]) is not int or not 0 <= record["timestamp"] <= 2**63 - 1):
        raise ValueError("timestamp must be a nonnegative 64-bit integer")
    for field in ("question", "answer"):
        if record.get(field) is not None and not isinstance(record[field], str):
            raise ValueError(f"{field} must be text or null")
    if "orderedData" in record and not isinstance(record["orderedData"], list):
        raise ValueError("orderedData must be an array")
    messages = record.setdefault("chatMessages", [])
    if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
        raise ValueError("chatMessages must be an array of objects")
    # Check serializability now, before opening a write transaction; detach mutable input.
    return json.loads(encode(record))


class ReportRepository:
    def __init__(self, database):
        self.database = database

    def _get(self, conn, report_id, *, metadata=True):
        row = conn.execute(select(reports).where(reports.c.report_id == report_id)).mappings().first()
        return self._decode(conn, row, metadata=metadata) if row else None

    def _decode(self, conn, row, *, metadata=True):
        result = json.loads(row["payload_json"])
        result["chatMessages"] = [json.loads(item) for item in conn.execute(
            select(report_chats.c.payload_json).where(report_chats.c.report_id == row["report_id"])
            .order_by(report_chats.c.position)).scalars()]
        if metadata:
            result.update(origin=row["origin"], lineage_status=row["lineage_status"], report_version=row["current_version"])
        return result

    def get_report(self, report_id):
        with self.database.read() as conn:
            return self._get(conn, report_id)

    def list_reports(self, report_ids=None, *, limit=None, offset=0):
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError("limit must be positive")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be nonnegative")
        query = select(reports).order_by(reports.c.timestamp.desc(), reports.c.report_id)
        if report_ids is not None:
            query = query.where(reports.c.report_id.in_(report_ids))
        query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        with self.database.read() as conn:
            return [self._decode(conn, row) for row in conn.execute(query).mappings()]

    def _upsert(self, conn, report_id, record, *, origin="client"):
        current = conn.execute(select(reports).where(reports.c.report_id == report_id)).mappings().first()
        if current and origin == "client" and "timestamp" in record:
            record = {**record, "timestamp": max(record["timestamp"], current["timestamp"])}
        payload = {k: v for k, v in record.items() if k != "chatMessages"}
        content = {k: v for k, v in payload.items() if k != "timestamp"}
        digest = fingerprint(content)
        changed = not current or current["content_hash"] != digest
        version = (current["current_version"] + int(changed)) if current else 1
        values = dict(payload_json=encode(payload), timestamp=record.get("timestamp", 0),
                      current_version=version, content_hash=digest,
                      origin=current["origin"] if current else origin, lineage_status="unavailable")
        if current:
            conn.execute(update(reports).where(reports.c.report_id == report_id).values(**values))
        else:
            conn.execute(insert(reports).values(report_id=report_id, **values))
        if changed:
            conn.execute(insert(report_versions).values(report_id=report_id, version=version,
                         payload_json=encode(content), content_hash=digest))
        old_messages = conn.execute(select(report_chats.c.payload_json).where(
            report_chats.c.report_id == report_id).order_by(report_chats.c.position)).scalars().all()
        encoded_messages = [encode(message) for message in record["chatMessages"]]
        prefix = 0
        while prefix < min(len(old_messages), len(encoded_messages)) and old_messages[prefix] == encoded_messages[prefix]:
            prefix += 1
        # Keep the identity and original report version of unchanged messages.
        conn.execute(delete(report_chats).where(report_chats.c.report_id == report_id,
                                              report_chats.c.position >= prefix))
        for i in range(prefix, len(encoded_messages)):
            conn.execute(insert(report_chats).values(report_id=report_id, position=i,
                         message_id=uuid4().hex, report_version=version, payload_json=encoded_messages[i]))

    def upsert_report(self, report_id, report):
        record = normalize_report(report_id, report)
        with self.database.write() as conn:
            self._upsert(conn, report_id, record)

    def patch_report(self, report_id, changes, *, timestamp):
        with self.database.write() as conn:
            current = self._get(conn, report_id, metadata=False)
            if current is None:
                return False
            updated = {**current, **{k: v for k, v in changes.items() if v is not None and k not in STORAGE_FIELDS},
                       "id": report_id, "timestamp": max(timestamp, current.get("timestamp", 0))}
            self._upsert(conn, report_id, normalize_report(report_id, updated))
            return True

    def append_chat_messages(self, report_id, messages, *, timestamp, expected_version=None):
        with self.database.write() as conn:
            current = self._get(conn, report_id)
            if current is None:
                return False
            if expected_version is not None and current["report_version"] != expected_version:
                raise ReportVersionConflict("Report changed while generating the reply")
            current["chatMessages"].extend(messages)
            current["timestamp"] = max(timestamp, current.get("timestamp", 0))
            self._upsert(conn, report_id, normalize_report(report_id, current))
            return True

    def delete_report(self, report_id):
        with self.database.write() as conn:
            return conn.execute(delete(reports).where(reports.c.report_id == report_id)).rowcount > 0
