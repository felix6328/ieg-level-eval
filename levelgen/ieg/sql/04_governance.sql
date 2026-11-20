CREATE TABLE IF NOT EXISTS bad_cases (
    id TEXT PRIMARY KEY, output_id TEXT NOT NULL REFERENCES outputs(id),
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
    experiment_id TEXT NOT NULL REFERENCES experiments(id), first_divergence TEXT NOT NULL,
    root_cause TEXT NOT NULL, confirmed INTEGER NOT NULL, reviewer TEXT, note TEXT NOT NULL,
    state TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(output_id,evaluation_id)
);
CREATE TABLE IF NOT EXISTS golden_cases (
    id TEXT PRIMARY KEY, bad_case_id TEXT NOT NULL REFERENCES bad_cases(id), title TEXT NOT NULL,
    spec TEXT NOT NULL, assertions TEXT NOT NULL, state TEXT NOT NULL,
    dataset_version TEXT REFERENCES dataset_versions(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS golden_events (
    id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES golden_cases(id), state TEXT NOT NULL,
    reviewer TEXT, reason TEXT NOT NULL, evidence TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rewrites (
    base_output TEXT PRIMARY KEY REFERENCES outputs(id),
    run_id TEXT NOT NULL UNIQUE REFERENCES generation_runs(id), reason TEXT NOT NULL,
    baseline_evaluation TEXT NOT NULL REFERENCES evaluations(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rewrite_archive (
    source_id TEXT PRIMARY KEY REFERENCES archive(id), recorded TEXT NOT NULL
);
