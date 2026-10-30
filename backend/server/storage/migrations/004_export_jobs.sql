CREATE TABLE export_jobs (
    job_id TEXT NOT NULL PRIMARY KEY,
    report_id TEXT NOT NULL,
    report_version INTEGER NOT NULL,
    format TEXT NOT NULL CHECK(format IN ('pdf','docx','md')),
    renderer_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
    fencing_token INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_until REAL,
    path TEXT,
    artifact_hash TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(report_id,report_version) REFERENCES report_versions(report_id,version) ON DELETE CASCADE,
    UNIQUE(report_id,report_version,format,renderer_version)
);
CREATE INDEX export_queue_idx ON export_jobs(status,created_at);
