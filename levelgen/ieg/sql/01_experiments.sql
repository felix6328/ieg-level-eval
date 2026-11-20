CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset_versions (
    id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id), number INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('DRAFT','FROZEN')), source TEXT NOT NULL, hash TEXT NOT NULL,
    note TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(dataset_id,number)
);
CREATE TABLE IF NOT EXISTS tasks (
    version_id TEXT NOT NULL REFERENCES dataset_versions(id), task_id TEXT NOT NULL, spec TEXT NOT NULL,
    split TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(version_id,task_id)
);
CREATE TABLE IF NOT EXISTS archive (
    id TEXT PRIMARY KEY, arm TEXT NOT NULL, task_id TEXT NOT NULL, sample INTEGER NOT NULL,
    record TEXT NOT NULL, source TEXT NOT NULL, UNIQUE(arm,task_id,sample)
);
CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY, template TEXT NOT NULL, messages TEXT NOT NULL, hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_configs (
    id TEXT PRIMARY KEY, provider TEXT NOT NULL, model TEXT NOT NULL, prompt_id TEXT NOT NULL REFERENCES prompts(id),
    temperature REAL NOT NULL, max_tokens INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, dataset_version TEXT NOT NULL REFERENCES dataset_versions(id),
    mode TEXT NOT NULL CHECK(mode IN ('REPLAY','MOCK','REAL')), config TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS generation_runs (
    id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(id), model_config_id TEXT NOT NULL,
    task_id TEXT NOT NULL, sample INTEGER NOT NULL, spec TEXT NOT NULL, config TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
    created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT, error TEXT,
    UNIQUE(experiment_id,model_config_id,task_id,sample)
);
CREATE INDEX IF NOT EXISTS generation_queue ON generation_runs(status,created_at,id);
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES generation_runs(id), number INTEGER NOT NULL,
    request TEXT NOT NULL, response TEXT, cost_estimate REAL, latency REAL, error TEXT,
    started_at TEXT NOT NULL, completed_at TEXT, UNIQUE(run_id,number)
);
CREATE TABLE IF NOT EXISTS outputs (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES generation_runs(id),
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(id), raw TEXT NOT NULL, parsed TEXT,
    origin TEXT NOT NULL, source_id TEXT REFERENCES archive(id), created_at TEXT NOT NULL
);
