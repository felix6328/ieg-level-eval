"""Experiment snapshots, source-aware execution, and durable run attempts."""
from contextlib import contextmanager
from threading import Event, Thread
import fcntl
import logging

from . import provider
from .store import BASE_FIELDS, Invalid, dump, get, load, now, uid

logger = logging.getLogger(__name__)


class Experiments:
    def __init__(self, store):
        self.store = store

    def create(self, config):
        mode = config["mode"]
        if mode == "REAL" and not provider.real_enabled():
            raise Invalid("REAL 尚未启用，请配置环境变量")
        if mode == "REPLAY" and (config["temperature"] is not None or config["max_tokens"] is not None
                                 or config["model_override"] or config["prompt_override"]):
            raise Invalid("历史 Replay 固定使用原模型、模板和采样参数")
        with self.store.connect(True) as db:
            version = get(db, "SELECT * FROM dataset_versions WHERE id=?", (config["dataset_version"],))
            if version["state"] != "FROZEN":
                raise Invalid("请选择已冻结的数据集版本")
            tasks = self.store.read_tasks(db, version["id"])
            if config["task_ids"]:
                chosen = set(config["task_ids"])
                tasks = [task for task in tasks if task["id"] in chosen]
                if len(tasks) != len(chosen):
                    raise Invalid("所选任务不在此数据版本")
            if not tasks:
                raise Invalid("数据集版本没有可运行的任务")
            model_ids = list(dict.fromkeys(config["models"]))
            stamp, ident = now(), uid()
            if not config["name"].strip() or not model_ids:
                raise Invalid("请填写实验名并选择生成组")
            frozen = {"dataset_hash": version["hash"], **config}
            configs = []
            for model_id in model_ids:
                snapshot = dict(get(db, "SELECT * FROM model_configs WHERE id=?", (model_id,)))
                prompt = get(db, "SELECT * FROM prompts WHERE id=?", (config["prompt_override"] or snapshot["prompt_id"],))
                snapshot.update(prompt_id=prompt["id"], pieces=load(prompt["messages"]), prompt_hash=prompt["hash"])
                for field in ("temperature", "max_tokens"):
                    if config[field] is not None:
                        snapshot[field] = config[field]
                if config["model_override"]:
                    snapshot["model"] = config["model_override"]
                if mode == "REAL":
                    snapshot["price_cny_per_m"] = provider.config_price(snapshot["model"])
                configs.append(snapshot)
            frozen["model_snapshots"] = configs
            db.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?)",
                       (ident, config["name"].strip(), version["id"], mode, dump(frozen), stamp))
            for item in configs:
                for spec in tasks:
                    for sample in range(config["repeats"]):
                        snap = {**item, "mode": mode, "seed": config["seed"] + sample,
                                "budget_cny": config["budget_cny"]}
                        db.execute("""INSERT INTO generation_runs(id,experiment_id,model_config_id,task_id,sample,
                                      spec,config,status,created_at) VALUES(?,?,?,?,?,?,?,'PENDING',?)""",
                                   (uid(), ident, item["id"], spec["id"], sample, dump(spec), dump(snap), stamp))
        return {"id": ident, "queued": len(tasks) * len(configs) * config["repeats"]}

    def list(self):
        with self.store.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT e.id,e.name,e.mode,e.dataset_version,e.created_at,count(g.id) total,
                       sum(g.status='PENDING') pending,sum(g.status='RUNNING') running,
                       sum(g.status='FAILED') failed,sum(g.status='SUCCEEDED') succeeded
                FROM experiments e JOIN generation_runs g ON g.experiment_id=e.id
                WHERE json_extract(g.config,'$.rewrite_for') IS NULL
                GROUP BY e.id ORDER BY e.created_at DESC""")]

    def detail(self, ident):
        with self.store.connect() as db:
            experiment = dict(get(db, "SELECT * FROM experiments WHERE id=?", (ident,)))
            experiment["config"] = load(experiment["config"])
            experiment["runs"] = [dict(row) for row in db.execute("""
                SELECT g.id,g.model_config_id,g.task_id,g.sample,g.status,g.error,g.started_at,g.completed_at,
                       o.id output_id,o.source_id,o.origin
                FROM generation_runs g LEFT JOIN outputs o ON o.attempt_id=(SELECT id FROM attempts
                  WHERE run_id=g.id ORDER BY number DESC LIMIT 1)
                WHERE g.experiment_id=? AND json_extract(g.config,'$.rewrite_for') IS NULL
                ORDER BY g.model_config_id,g.task_id,g.sample""", (ident,))]
            return experiment

    def run_detail(self, ident):
        with self.store.connect() as db:
            row = dict(get(db, "SELECT * FROM generation_runs WHERE id=?", (ident,)))
            for k in ("spec", "config"):
                row[k] = load(row[k])
            attempts = []
            for result in db.execute("""SELECT a.*,o.id output_id,o.origin,o.source_id,o.raw,o.parsed
                FROM attempts a LEFT JOIN outputs o ON o.attempt_id=a.id WHERE a.run_id=? ORDER BY a.number""",
                                     (ident,)):
                entry = dict(result)
                for k in ("request", "response", "parsed"):
                    entry[k] = load(entry[k]) if entry[k] else None
                attempts.append(entry)
            row["attempts"] = attempts
            return row

    def retry(self, ident):
        with self.store.connect(True) as db:
            row = get(db, "SELECT status FROM generation_runs WHERE id=?", (ident,))
            if row["status"] != "FAILED":
                raise Invalid("仅失败任务可以重试")
            db.execute("""UPDATE generation_runs SET status='PENDING',started_at=NULL,
                          completed_at=NULL,error=NULL WHERE id=?""", (ident,))
        return {"id": ident}

    def claim(self):
        with self.store.connect(True) as db:
            pending = db.execute("""SELECT * FROM generation_runs WHERE status='PENDING'
                                  ORDER BY created_at,id LIMIT 1""").fetchone()
            if pending is None:
                return None
            db.execute("UPDATE generation_runs SET status='RUNNING',started_at=? WHERE id=?", (now(), pending["id"]))
            return dict(pending)

    def recover(self):
        with self.store.connect(True) as db:
            stamp = now()
            db.execute("""UPDATE attempts SET completed_at=?,error='执行中断，远端状态未知',
                          response=CASE WHEN json_extract(request,'$.mode')='REAL'
                          THEN '{"remote_status":"UNKNOWN"}' ELSE NULL END
                          WHERE completed_at IS NULL""", (stamp,))
            db.execute("""UPDATE generation_runs SET status='FAILED',completed_at=?,
                          error='服务重启，真实费用可能未知'
                          WHERE status='RUNNING' AND json_extract(config,'$.mode')='REAL'""", (stamp,))
            db.execute("""UPDATE generation_runs SET status='PENDING',started_at=NULL,error=NULL
                          WHERE status='RUNNING'""")

    def replay(self, run, spec, config):
        with self.store.connect() as db:
            if config.get("replay_rewrite_id"):
                archive = get(db, "SELECT * FROM archive WHERE id=?", (config["replay_rewrite_id"],))
                record = load(archive["record"])
                return provider.Reply(record["raw"], {"archive":record,"source":archive["source"]},
                                      record["usage"]["latency_s"],0.0), archive["id"],record["level"]
            archive = db.execute("SELECT * FROM archive WHERE arm=? AND task_id=? AND sample=?",
                                 (config["id"], spec.get("replay_spec_id", spec["spec_id"]), run["sample"])).fetchone()
        if archive is None:
            raise Invalid("该任务或重复序号没有匹配的历史生成记录")
        record = load(archive["record"])
        if any((spec.get(k) or "") != (record["spec"].get(k) or "") for k in (*BASE_FIELDS, "theme_hint")):
            raise Invalid("当前任务约束与历史记录不一致")
        return provider.Reply(record["raw"], {"archive": record, "source": archive["source"]},
                              record["usage"]["latency_s"], 0.0), archive["id"], record["level"]

    def execute(self, run):
        spec, config = load(run["spec"]), load(run["config"])
        messages = config.get("rewrite_messages") or provider.render(spec, config["pieces"])
        body = {"model": config["model"], "messages": messages, "max_tokens": config["max_tokens"],
                "temperature": config["temperature"], "seed": config["seed"], "stream": False}
        if config["mode"] == "REPLAY":
            body.pop("seed")
        attempt, stamp = uid(), now()
        with self.store.connect(True) as db:
            number = db.execute("SELECT coalesce(max(number),0)+1 FROM attempts WHERE run_id=?",
                                (run["id"],)).fetchone()[0]
            db.execute("""INSERT INTO attempts(id,run_id,number,request,started_at) VALUES(?,?,?,?,?)""",
                       (attempt, run["id"], number, dump({"mode": config["mode"], "body": body,
                                                            "reconstructed": config["mode"] == "REPLAY"}), stamp))
        reply, source, parsed = None, None, None
        try:
            mode = config["mode"]
            if mode == "REPLAY":
                reply, source, parsed = self.replay(run, spec, config)
            else:
                reply = provider.mock(spec, run["sample"]) if mode == "MOCK" else self.real(run, config, body)
                parsed = provider.parse(reply.raw)
            failure = reply.error or (None if isinstance(parsed, dict) else "生成内容无法解析为 JSON 对象")
        except Invalid as exc:
            failure = str(exc)
        except Exception:
            logger.exception("IEG generation failed")
            failure = "执行异常，请查看服务日志"
        with self.store.connect(True) as db:
            finished = now()
            db.execute("""UPDATE attempts SET response=?,cost_estimate=?,latency=?,error=?,completed_at=? WHERE id=?""",
                       (dump(reply.response) if reply else None, reply.cost if reply else None,
                        reply.latency if reply else None, failure, finished, attempt))
            output_id = None
            if reply and (reply.raw or source):
                output_id = uid()
                db.execute("INSERT INTO outputs VALUES(?,?,?,?,?,?,?,?)",
                           (output_id, run["id"], attempt, reply.raw, dump(parsed) if parsed is not None else None,
                            config["mode"], source, finished))
            db.execute("UPDATE generation_runs SET status=?,completed_at=?,error=? WHERE id=?",
                       ("FAILED" if failure else "SUCCEEDED", finished, failure, run["id"]))
        return output_id

    def real(self, run, config, body):
        with self.store.connect() as db:
            attempts = db.execute("""SELECT a.* FROM attempts a JOIN generation_runs g ON a.run_id=g.id
                                     WHERE g.experiment_id=? AND a.completed_at IS NOT NULL""",
                                  (run["experiment_id"],)).fetchall()
        if any(row["response"] and row["cost_estimate"] is None for row in attempts):
            raise Invalid("存在费用未知的远端调用，暂停后续付费请求")
        spent = sum(row["cost_estimate"] or 0 for row in attempts)
        return provider.real(body, config["budget_cny"] - spent, config["price_cny_per_m"])


class Worker:
    """Single worker per workspace, with exclusive ownership across app processes."""

    def __init__(self, experiments, after=None):
        self.experiments = experiments
        self.after = after
        self.stop = Event()

    def one(self):
        run = self.experiments.claim()
        if run is None:
            return False
        output = self.experiments.execute(run)
        if output and self.after:
            self.after(output)
        return True

    def serve(self):
        lock_path = self.experiments.store.path.with_suffix(".worker.lock")
        with lock_path.open("a+b") as lock:
            while not self.stop.is_set():
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    self.stop.wait(0.5)
            if self.stop.is_set():
                return
            self.experiments.recover()
            if self.after:
                with self.experiments.store.connect() as db:
                    remaining = [r[0] for r in db.execute("""
                      SELECT id FROM outputs o WHERE NOT EXISTS
                        (SELECT 1 FROM triage_decisions WHERE output_id=o.id) ORDER BY created_at
                    """)]
                for output in remaining:
                    if self.stop.is_set():
                        return
                    try:
                        self.after(output)
                    except Exception:
                        logger.exception("IEG could not recover evaluation %s", output)
            while not self.stop.is_set():
                try:
                    if not self.one():
                        self.stop.wait(0.25)
                except Exception:
                    logger.exception("IEG worker step failed")
                    self.stop.wait(0.5)

    @contextmanager
    def background(self):
        thread = Thread(target=self.serve, daemon=True)
        thread.start()
        try:
            yield
        finally:
            self.stop.set()
            thread.join(timeout=2)
