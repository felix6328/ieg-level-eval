CREATE TABLE IF NOT EXISTS human_reviews (
    id TEXT PRIMARY KEY, output_id TEXT NOT NULL REFERENCES outputs(id),
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id), reviewer TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('HUMAN','MODEL_ASSISTED')),
    scores TEXT NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('ACCEPT','REJECT')),
    tags TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS human_review_output ON human_reviews(output_id,created_at);
CREATE TABLE IF NOT EXISTS triage_decisions (
    id TEXT PRIMARY KEY, output_id TEXT NOT NULL REFERENCES outputs(id),
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id), status TEXT NOT NULL
        CHECK(status IN ('AUTO_PASS','AUTO_BLOCK','NEEDS_HUMAN_REVIEW','HUMAN_ACCEPT','HUMAN_REJECT')),
    prior_id TEXT REFERENCES triage_decisions(id), reviewer TEXT, policy TEXT NOT NULL,
    reason TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS triage_output ON triage_decisions(output_id,created_at);
