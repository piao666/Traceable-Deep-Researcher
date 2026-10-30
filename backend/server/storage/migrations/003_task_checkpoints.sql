ALTER TABLE research_tasks ADD COLUMN projection_json TEXT NOT NULL DEFAULT '{"draft":"","attempt_id":null}';
CREATE TABLE task_checkpoints (
    research_id TEXT NOT NULL REFERENCES research_tasks(research_id) ON DELETE CASCADE,
    stage_key TEXT NOT NULL,
    base_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(research_id, stage_key)
);
