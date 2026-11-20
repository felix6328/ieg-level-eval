CREATE TABLE IF NOT EXISTS archive_judges (
    source_id TEXT PRIMARY KEY REFERENCES archive(id), record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS terra_reference (
    source_id TEXT PRIMARY KEY REFERENCES archive(id), record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY, output_id TEXT NOT NULL REFERENCES outputs(id),
    ruleset TEXT NOT NULL, config TEXT NOT NULL, hard_pass INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS evaluation_output ON evaluations(output_id,created_at);
CREATE TABLE IF NOT EXISTS rule_results (
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id), rule_id TEXT NOT NULL, record TEXT NOT NULL,
    PRIMARY KEY(evaluation_id,rule_id)
);
CREATE TABLE IF NOT EXISTS judge_results (
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id), judge_id TEXT NOT NULL, model TEXT NOT NULL,
    source TEXT NOT NULL, status TEXT NOT NULL, record TEXT NOT NULL,
    PRIMARY KEY(evaluation_id,judge_id)
);
