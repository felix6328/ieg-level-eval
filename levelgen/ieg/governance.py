"""Bad Case trace, Golden Case lifecycle, and one-shot rewrite."""
from collections import defaultdict

from .evaluation import DIMS
from .store import ROOT, Invalid, dump, get, jsonl, load, now, uid

ROOT_CAUSES = ("Prompt Constraint Missing", "Model Capability Limitation", "Context Loss", "State Inconsistency",
               "Schema Error", "Game Logic Error", "Evaluation Error", "Unknown")


def trace(run, ev, decision):
    attempt = next((a for a in run["attempts"] if a["output_id"] == ev["output_id"]), {})
    result = [{"node": "GENERATION", "evidence": "历史产物可回溯" if attempt.get("source_id") else "已记录生成响应",
               "time": attempt.get("completed_at"), "diverged": False}]
    checks = ev["rules"]
    schema = [r for r in checks if r["rule_id"] in {"H1_json可解析", "SCHEMA"} and r["status"] == "FAIL"]
    deterministic = [r for r in checks if r["rule_id"] not in {"H1_json可解析", "SCHEMA"} and r["status"] == "FAIL"]
    result.append({"node": "PARSE_SCHEMA", "evidence": schema, "time": ev["created_at"], "diverged": bool(schema)})
    result.append({"node": "RULES", "evidence": deterministic, "time": ev["created_at"], "diverged": bool(deterministic)})
    bad = [j["id"] for j in ev["judges"] if j["status"] == "INVALID"]
    if bad:
        result.append({"node": "JUDGE_EVIDENCE", "evidence": bad, "time": ev["created_at"], "diverged": True})
    if decision:
        result.append({"node": "TRIAGE", "evidence": decision["reason"], "time": decision["created_at"],
                       "diverged": decision["status"] in {"AUTO_BLOCK", "HUMAN_REJECT"}})
    return result


def evaluate_assertions(assertions, evaluation, raw):
    checked = []
    rules = {r["rule_id"]:r for r in evaluation["rules"]}
    for item in assertions:
        if item["type"] == "hard_pass":
            actual = evaluation["hard_pass"]
        elif item["type"] == "rule_pass":
            actual = rules.get(item["value"], {}).get("status") == "PASS"
        else:
            actual = item["value"] in raw
        checked.append({**item, "pass": bool(actual)})
    return checked


def validate_assertions(assertions):
    if not 1 <= len(assertions) <= 20 or any(
            not isinstance(a, dict) or a.get("type") not in {"hard_pass", "rule_pass", "contains"}
            or (a["type"] != "hard_pass" and (not isinstance(a.get("value"), str) or not a["value"].strip()))
            for a in assertions):
        raise Invalid("需要 1 至 20 条有效断言，可用 hard_pass、rule_pass 或 contains")


class Governance:
    def __init__(self, store, experiments, evaluations, reviews):
        self.store, self.experiments, self.evaluations, self.reviews = store, experiments, evaluations, reviews
        with store.connect(True) as db:
            if not db.execute("SELECT 1 FROM rewrite_archive LIMIT 1").fetchone():
                for linked in jsonl(ROOT / "eval/rewrite_results.jsonl"):
                    ident = linked["level_id"]
                    record = load((ROOT / f"data/rewrites/{ident}.json").read_text(encoding="utf-8"))
                    db.execute("INSERT INTO archive VALUES(?,?,?,?,?,?)",
                               (ident, record["arm"], linked["spec_id"], record.get("sample",0),
                                dump(record), "wxg-v1.0:rewrite"))
                    db.execute("INSERT INTO rewrite_archive VALUES(?,?)", (linked["base_level_id"], dump(linked)))
                    db.execute("INSERT INTO archive_judges VALUES(?,?)", (ident, dump(linked["v3_after"])))

    def context(self, output):
        with self.store.connect() as db:
            row = dict(get(db, """SELECT o.*,g.config,g.experiment_id,g.spec,g.task_id,g.sample,g.model_config_id
                       FROM outputs o JOIN generation_runs g ON g.id=o.run_id WHERE o.id=?""", (output,)))
        return row, self.evaluations.detail(output), self.experiments.run_detail(row["run_id"])

    def trace(self, output):
        _, ev, run = self.context(output)
        decisions = self.reviews.history(output)["decisions"]
        nodes = trace(run, ev, decisions[0] if decisions else None)
        return {"nodes": nodes, "first_observable_divergence": next((n for n in nodes if n["diverged"]), None)}

    def create_bad(self, output, cause, note, reviewer):
        if cause not in ROOT_CAUSES:
            raise Invalid("根因类别无效")
        row, ev, _ = self.context(output)
        point = self.trace(output)["first_observable_divergence"]
        hint = point["node"] if point else "UNKNOWN"
        confirmed = bool(reviewer.strip() and note.strip() and cause != "Unknown")
        with self.store.connect(True) as db:
            known = db.execute("SELECT id FROM bad_cases WHERE output_id=? AND evaluation_id=?",
                               (output,ev["id"])).fetchone()
            if known:
                return self.read_bad(db, known["id"])
            ident = uid()
            db.execute("INSERT INTO bad_cases VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (ident, output, ev["id"], row["experiment_id"], hint, cause, confirmed,
                        reviewer.strip() or None, note.strip(), "OPEN", now()))
            return self.read_bad(db, ident)

    @staticmethod
    def read_bad(db, ident):
        return dict(get(db, "SELECT * FROM bad_cases WHERE id=?", (ident,)))

    def update_bad(self, ident, *, cause, note, reviewer, state):
        if cause not in ROOT_CAUSES or state not in {"OPEN","INVESTIGATING","RESOLVED"}:
            raise Invalid("根因或状态无效")
        if not (reviewer.strip() and note.strip()):
            raise Invalid("更新根因需要记录审核人与理由")
        with self.store.connect(True) as db:
            self.read_bad(db, ident)
            db.execute("UPDATE bad_cases SET root_cause=?,note=?,reviewer=?,confirmed=?,state=? WHERE id=?",
                       (cause,note,reviewer,cause!="Unknown",state,ident))
            return self.read_bad(db, ident)

    def list(self):
        with self.store.connect() as db:
            return {"bad_cases":[dict(r) for r in db.execute("SELECT * FROM bad_cases ORDER BY created_at DESC")],
                    "golden_cases":[self.golden(db, r["id"]) for r in db.execute("SELECT * FROM golden_cases ORDER BY created_at DESC")]}

    def create_golden(self, bad_id, title, task, assertions):
        validate_assertions(assertions)
        if not title.strip():
            raise Invalid("请填写案例名称")
        ident = uid()
        with self.store.connect(True) as db:
            bad = self.read_bad(db, bad_id)
            original = load(get(db, """SELECT g.spec FROM generation_runs g
                            JOIN outputs o ON o.run_id=g.id WHERE o.id=?""", (bad["output_id"],))[0])
            original_archive = original.get("replay_spec_id", original["spec_id"])
            spec = {**original, **task, "spec_id": f"golden-{ident[:12]}", "replay_spec_id": original_archive,
                    "split": "golden", "assertions": assertions, "source_bad_case": bad_id}
            self.store.validate_specs([spec])
            db.execute("INSERT INTO golden_cases VALUES(?,?,?,?,?,'DRAFT',NULL,?)",
                       (ident, bad_id, title.strip(), dump(spec), dump(assertions), now()))
            self.event(db,ident,"DRAFT",None,"从 Bad Case 建立候选",None)
            return self.golden(db, ident)

    def golden_action(self, ident, action, reviewer, reason):
        if action != "validate" and not (reviewer.strip() and reason.strip()):
            raise Invalid("请提供人工操作人和理由")
        with self.store.connect(True) as db:
            case = self.golden(db, ident)
            current = case["state"]
            permitted = {("DRAFT","validate"):"VALIDATING", ("VALIDATING","approve"):"APPROVED",
                         ("VALIDATING","reject"):"DRAFT", ("APPROVED","publish"):"ACTIVE",
                         ("ACTIVE","deprecate"):"DEPRECATED"}
            target = permitted.get((current, action))
            if not target:
                raise Invalid("当前状态无法执行该操作")
            validation = None
            if action == "validate":
                bad = self.read_bad(db, case["bad_case_id"])
                ev = self.evaluations.detail(bad["output_id"])
                raw = get(db,"SELECT raw FROM outputs WHERE id=?", (bad["output_id"],))[0]
                validation = evaluate_assertions(case["assertions"],ev,raw)
            db.execute("UPDATE golden_cases SET state=? WHERE id=?", (target,ident))
            version = None
            if action in {"publish","deprecate"}:
                db.execute("INSERT OR IGNORE INTO datasets VALUES('ieg-golden','ieg','策划 Golden Case',?)", (now(),))
                active = [load(row["spec"]) for row in db.execute("SELECT spec FROM golden_cases WHERE state='ACTIVE' ORDER BY id")]
                # Retirement may create an empty version while older versions remain runnable.
                version = self.store.add_version(db,"ieg-golden","",active,reason)["id"]
                self.store.freeze_version(db,version)
                if action == "publish":
                    db.execute("UPDATE golden_cases SET dataset_version=? WHERE id=?", (version,ident))
            self.event(db, ident, target, reviewer.strip() or None, reason or "在来源输出执行候选断言",
                       {"assertions":validation,"dataset_version":version})
            return self.golden(db,ident)

    @staticmethod
    def event(db, ident, state, reviewer, reason, evidence):
        db.execute("INSERT INTO golden_events VALUES(?,?,?,?,?,?,?)",
                   (uid(),ident,state,reviewer,reason,dump(evidence) if evidence else None,now()))

    @staticmethod
    def golden(db, ident):
        row = dict(get(db,"SELECT * FROM golden_cases WHERE id=?", (ident,)))
        row["spec"],row["assertions"] = load(row["spec"]),load(row["assertions"])
        row["events"] = [{**dict(x),"evidence":load(x["evidence"]) if x["evidence"] else None} for x in db.execute(
            "SELECT * FROM golden_events WHERE case_id=? ORDER BY created_at", (ident,))]
        return row

    def rewrite(self, output, reason):
        row, evaluation, run = self.context(output)
        if not reason.strip():
            raise Invalid("请记录修复原因或修改要求")
        cfg = load(row["config"])
        if cfg.get("rewrite_for"):
            raise Invalid("每个样本最多自动重写一次")
        with self.store.connect(True) as db:
            existing = db.execute("SELECT run_id FROM rewrites WHERE base_output=?", (output,)).fetchone()
            if existing:
                raise Invalid("此输出已有一次重写记录")
            if row["origin"] == "REPLAY":
                historic = db.execute("SELECT recorded FROM rewrite_archive WHERE source_id=?", (row["source_id"],)).fetchone()
                if not historic:
                    raise Invalid("这份历史输出没有已归档的重写，不能用 Replay 伪造")
                cfg["replay_rewrite_id"] = load(historic[0])["level_id"]
            attempt = next(a for a in run["attempts"] if a["output_id"] == output)
            messages = attempt["request"]["body"]["messages"]
            cfg.update(rewrite_for=output, rewrite_messages=[
                *messages, {"role":"assistant","content":row["raw"]},
                {"role":"user","content":f"请按下列问题重写，保留未涉内容并输出完整关卡 JSON。\n{reason.strip()}"}
            ])
            ident, stamp = uid(), now()
            db.execute("""INSERT INTO generation_runs(id,experiment_id,model_config_id,task_id,sample,
                            spec,config,status,created_at) VALUES(?,?,?,?,?,?,?,'PENDING',?)""",
                       (ident,row["experiment_id"],f"{row['model_config_id']}-rw-{output[:12]}",row["task_id"],
                        row["sample"],row["spec"],dump(cfg),stamp))
            db.execute("INSERT INTO rewrites VALUES(?,?,?,?,?)",
                       (output,ident,reason,evaluation["id"],stamp))
        return {"run_id":ident}

    def rewrite_detail(self, output):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM rewrites WHERE base_output=?", (output,)).fetchone()
            if not row:
                return None
            original = get(db, """SELECT a.latency,a.cost_estimate FROM outputs o JOIN attempts a ON a.id=o.attempt_id
                                    WHERE o.id=?""", (output,))
            original_ev = get(db, "SELECT * FROM evaluations WHERE id=?", (row["baseline_evaluation"],))
            baseline_rules = [load(x[0]) for x in db.execute("SELECT record FROM rule_results WHERE evaluation_id=?",
                                                           (row["baseline_evaluation"],))]
            archived = db.execute("SELECT recorded FROM rewrite_archive WHERE source_id=(SELECT source_id FROM outputs WHERE id=?)",
                                  (output,)).fetchone()
        run = self.experiments.run_detail(row["run_id"])
        after = next((a for a in reversed(run["attempts"]) if a["output_id"]), None)
        result = {**dict(row), "run":run, "quality":"PENDING",
                  "before":{"hard_pass":bool(original_ev["hard_pass"]),"rules":baseline_rules},
                  "recorded_historical":load(archived[0]) if archived else None}
        if not after:
            result["quality"] = "FAILED" if run["status"]=="FAILED" else "PENDING"
            return result
        from .store import Missing
        try:
            ev = self.evaluations.detail(after["output_id"])
        except Missing:
            return result
        spec = run["spec"]
        checks = evaluate_assertions(spec.get("assertions",[]),ev,after["raw"])
        status = "BELOW_GATE" if not ev["hard_pass"] or not all(x["pass"] for x in checks) else "SEMANTIC_UNVERIFIED"
        semantic = [j for j in ev["judges"] if j["status"]=="VALID" and j["source"]=="REAL_JUDGE"]
        if len(semantic)>=2 and status=="SEMANTIC_UNVERIFIED":
            status = "MEETS_GATE" if all(min(j["scores"].values())>=3 for j in semantic) else "BELOW_GATE"
        result.update(after=ev,quality=status,assertions=checks,latency_delta=delta(after["latency"],original["latency"]),
                      cost_estimate_delta=delta(after["cost_estimate"],original["cost_estimate"]))
        return result


def delta(new, old):
    return new-old if new is not None and old is not None else None
