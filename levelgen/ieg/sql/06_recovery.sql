CREATE TABLE IF NOT EXISTS online_evaluation_guard (
    output_id TEXT PRIMARY KEY REFERENCES outputs(id),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bad_case_events (
    id TEXT PRIMARY KEY, bad_case_id TEXT NOT NULL REFERENCES bad_cases(id),
    record TEXT NOT NULL, created_at TEXT NOT NULL
);
