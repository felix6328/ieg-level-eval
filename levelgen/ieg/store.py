"""Isolated IEG SQLite workspace and read-only WXG baseline import."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import json
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "wxg-v1.0@7ab99c766b1f203ccc30033f81280dffad2b6183"
BASE_FIELDS = ("theme", "difficulty", "difficulty_def", "persona", "persona_desc")
DIMS = ("逻辑自洽性", "趣味性", "难度匹配度", "可玩性")


class Invalid(ValueError):
    """Input violates a workspace contract."""


class Missing(LookupError):
    """Record does not exist."""


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def load(value):
    return json.loads(value)


def sha(value):
    return sha256(dump(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def uid():
    return uuid4().hex


def jsonl(path):
    return [load(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def get(db, sql, args=()):
    row = db.execute(sql, args).fetchone()
    if row is None:
        raise Missing("记录不存在")
    return row


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            for migration in sorted(Path(__file__).with_name("sql").glob("*.sql")):
                db.executescript(migration.read_text(encoding="utf-8"))
        self.seed()

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seed(self):
        stamp = now()
        with self.connect(True) as db:
            if db.execute("SELECT id FROM datasets WHERE id='wxg24'").fetchone():
                return
            db.execute("INSERT INTO projects VALUES('ieg','LevelEval 2.0',?)", (stamp,))
            db.execute("INSERT INTO datasets VALUES('wxg24','ieg','文字冒险 24 题历史基线',?)", (stamp,))
            specs = load((ROOT / "data/eval_specs.json").read_text(encoding="utf-8"))
            db.execute("INSERT INTO dataset_versions VALUES(?,?,?,?,?,?,?,?)",
                       ("wxg24-v1", "wxg24", 1, "FROZEN", ORIGIN, sha(specs), "从 WXG 稳定版本导入", stamp))
            for spec in specs:
                db.execute("INSERT INTO tasks VALUES(?,?,?,?,?)",
                           ("wxg24-v1", spec["spec_id"], dump(spec), "legacy", stamp))
            for path in sorted((ROOT / "data/levels").glob("*.json")):
                rec = load(path.read_text(encoding="utf-8"))
                db.execute("INSERT INTO archive VALUES(?,?,?,?,?,?)",
                           (rec["level_id"], rec["arm"], rec["spec"]["spec_id"], rec.get("sample", 0), dump(rec), ORIGIN))
            for name, paths in {"gen_v1": ["gen_v1.txt"], "gen_v2": ["gen_v2_system.txt", "gen_v2_user.txt"]}.items():
                pieces = [(ROOT / "prompts" / path).read_text(encoding="utf-8") for path in paths]
                db.execute("INSERT INTO prompts VALUES(?,?,?,?,?)", (name, name, dump(pieces), sha(pieces), stamp))
            for key, model, prompt in (("A", "Qwen/Qwen2.5-7B-Instruct", "gen_v1"),
                                       ("B", "Qwen/Qwen2.5-7B-Instruct", "gen_v2"),
                                       ("C", "Qwen/Qwen2.5-72B-Instruct", "gen_v2")):
                db.execute("INSERT INTO model_configs VALUES(?,?,?,?,?,?,?)",
                           (key, "openai-compatible", model, prompt, 0.8, 1800, stamp))

    def catalog(self):
        with self.connect() as db:
            return {k: [dict(row) for row in db.execute(query)] for k, query in {
                "datasets": "SELECT * FROM datasets ORDER BY created_at",
                "versions": """SELECT v.*, d.name, (SELECT count(*) FROM tasks WHERE version_id=v.id) total
                              FROM dataset_versions v JOIN datasets d ON d.id=v.dataset_id
                              ORDER BY v.created_at DESC""",
                "models": "SELECT * FROM model_configs ORDER BY id",
                "prompts": "SELECT id,template,hash,created_at FROM prompts ORDER BY id",
            }.items()}

    def tasks(self, version):
        with self.connect() as db:
            get(db, "SELECT id FROM dataset_versions WHERE id=?", (version,))
            return self.read_tasks(db, version)

    @staticmethod
    def read_tasks(db, version):
        return [{"id": row["task_id"], "split": row["split"], **load(row["spec"])}
                for row in db.execute("SELECT * FROM tasks WHERE version_id=? ORDER BY task_id", (version,))]

    @staticmethod
    def validate_specs(tasks):
        if not 1 <= len(tasks) <= 1000:
            raise Invalid("数据集需包含 1 至 1000 条任务")
        seen = set()
        for spec in tasks:
            if not isinstance(spec, dict):
                raise Invalid("每条任务需要 JSON 对象")
            task_id = spec.get("spec_id")
            if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 120 or task_id in seen:
                raise Invalid("spec_id 无效或重复")
            seen.add(task_id)
            if any(not isinstance(spec.get(k), str) or not spec[k].strip() for k in BASE_FIELDS):
                raise Invalid(f"{task_id} 缺少主题、难度或画像")
            if spec["difficulty"] not in {"简单", "普通", "困难"}:
                raise Invalid(f"{task_id} 难度无效")
            if spec.get("split", "dev") not in {"dev", "validation", "holdout", "legacy", "golden"}:
                raise Invalid(f"{task_id} 划分无效")
            if any(k in spec and not isinstance(spec[k], str) for k in ("theme_hint", "persona_id", "replay_spec_id")):
                raise Invalid(f"{task_id} 可选文本字段无效")

    def version(self, *, dataset_id, name, tasks, note):
        self.validate_specs(tasks)
        with self.connect(True) as db:
            return self.add_version(db, dataset_id, name, tasks, note)

    @staticmethod
    def add_version(db, dataset_id, name, tasks, note):
        stamp, version = now(), uid()
        if dataset_id:
            get(db, "SELECT id FROM datasets WHERE id=?", (dataset_id,))
        else:
            if not name.strip():
                raise Invalid("请填写数据集名称")
            dataset_id = uid()
            db.execute("INSERT INTO datasets VALUES(?,?,?,?)", (dataset_id, "ieg", name.strip(), stamp))
        number = db.execute("SELECT coalesce(max(number),0)+1 FROM dataset_versions WHERE dataset_id=?",
                            (dataset_id,)).fetchone()[0]
        db.execute("INSERT INTO dataset_versions VALUES(?,?,?,?,?,?,?,?)",
                   (version, dataset_id, number, "DRAFT", "IEG", sha(tasks), note, stamp))
        for task in tasks:
            spec = {key: value for key, value in task.items() if key not in {"id", "split"}}
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?)",
                       (version, task["spec_id"], dump(spec), task.get("split", "dev"), stamp))
        return dict(get(db, "SELECT * FROM dataset_versions WHERE id=?", (version,)))

    def freeze(self, version):
        with self.connect(True) as db:
            return self.freeze_version(db, version)

    @staticmethod
    def freeze_version(db, version):
        row = get(db, "SELECT * FROM dataset_versions WHERE id=?", (version,))
        db.execute("UPDATE dataset_versions SET state='FROZEN' WHERE id=? AND state='DRAFT'", (version,))
        return {**row, "state": "FROZEN"}
