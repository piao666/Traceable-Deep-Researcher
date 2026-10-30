CREATE TABLE research_tasks (
    research_id TEXT PRIMARY KEY NOT NULL,
    request_json TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    credential_ref TEXT,
    status TEXT NOT NULL CHECK(status IN ('queued','running','cancel_requested','cancelled','succeeded','failed','interrupted','waiting_for_review')),
    review_status TEXT NOT NULL DEFAULT 'not_requested',
    current_attempt TEXT,
    fencing_token INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_until REAL,
    last_seq INTEGER NOT NULL DEFAULT 0,
    result_json TEXT,
    error_json TEXT,
    configuration_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX research_queue_idx ON research_tasks(status, created_at);
CREATE TABLE task_attempts (
    attempt_id TEXT PRIMARY KEY NOT NULL,
    research_id TEXT NOT NULL REFERENCES research_tasks(research_id),
    fencing_token INTEGER NOT NULL,
    owner TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    status TEXT NOT NULL,
    UNIQUE(research_id, fencing_token)
);
CREATE TABLE task_events (
    research_id TEXT NOT NULL REFERENCES research_tasks(research_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL CHECK(seq > 0),
    attempt_id TEXT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(research_id, seq)
);
ALTER TABLE reports ADD COLUMN task_id TEXT REFERENCES research_tasks(research_id);
CREATE UNIQUE INDEX reports_task_idx ON reports(task_id);
