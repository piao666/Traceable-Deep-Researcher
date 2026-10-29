-- A1 report storage foundation. Task execution tables follow in A2/A3.
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE reports (
    report_id TEXT NOT NULL PRIMARY KEY,
    payload_json TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    current_version INTEGER NOT NULL CHECK (current_version >= 1),
    content_hash TEXT NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('client', 'legacy_import')),
    lineage_status TEXT NOT NULL DEFAULT 'unavailable' CHECK (lineage_status = 'unavailable')
);
CREATE INDEX reports_timestamp_idx ON reports(timestamp DESC, report_id);
CREATE TABLE report_versions (
    report_id TEXT NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version >= 1),
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (report_id, version)
);
CREATE TRIGGER report_versions_no_update BEFORE UPDATE ON report_versions
BEGIN
    SELECT RAISE(ABORT, 'report versions are immutable');
END;
CREATE TABLE report_chats (
    report_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    message_id TEXT NOT NULL,
    report_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (report_id, position),
    UNIQUE (report_id, message_id),
    FOREIGN KEY (report_id, report_version) REFERENCES report_versions(report_id, version) ON DELETE CASCADE
);
CREATE TABLE legacy_batches (
    source_hash TEXT NOT NULL PRIMARY KEY,
    source_key TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE legacy_imports (
    source_hash TEXT NOT NULL REFERENCES legacy_batches(source_hash),
    report_id TEXT NOT NULL,
    source_key TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    PRIMARY KEY (source_hash, report_id)
);
CREATE INDEX legacy_source_report_idx ON legacy_imports(source_key, report_id);
