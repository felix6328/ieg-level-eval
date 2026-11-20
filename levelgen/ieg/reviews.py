"""Append-only triage decisions and explicit human judgments."""
from .evaluation import compare_pairs, fraction, valid_scores
from .store import Invalid, dump, get, load, now, uid

DEFAULT = {"min_judges": 2, "min_score": 3, "min_confidence": .7, "max_dimension_spread": 1}


def route(evaluation, policy):
    failures = [r["rule_id"] for r in evaluation["rules"] if r["status"] == "FAIL"]
    if failures:
        return "AUTO_BLOCK", "确定性阻断：" + "、".join(failures)
    checks = [j for j in evaluation["judges"] if j["source"] != "TERRA_MODEL_REFERENCE"]
    if len(checks) < policy["min_judges"]:
        return "NEEDS_HUMAN_REVIEW", "可用的独立语义评审数量不足"
    if any(j["status"] != "VALID" for j in checks):
        return "NEEDS_HUMAN_REVIEW", "语义证据、结构或可用性需要人工复核"
    if any(j["confidence"] is None or j["confidence"] < policy["min_confidence"] for j in checks):
        return "NEEDS_HUMAN_REVIEW", "评审置信度缺失或低于阈值"
    scores = [j["scores"] for j in checks]
    if any(max(s[d] for s in scores) - min(s[d] for s in scores) > policy["max_dimension_spread"]
           for d in scores[0]):
        return "NEEDS_HUMAN_REVIEW", "评审在关键维度分歧"
    if any(min(s.values()) < policy["min_score"] for s in scores):
        return "NEEDS_HUMAN_REVIEW", "至少一个语义维度低于门槛"
    return "AUTO_PASS", "硬规则、语义、证据、置信度和分歧均满足门槛"


def latest(db, table, output):
    row = db.execute(f"SELECT * FROM {table} WHERE output_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
                     (output,)).fetchone()
    return dict(row) if row else None


class Reviews:
    def __init__(self, store, evaluations):
        self.store = store
        self.evaluations = evaluations

    def policy_for(self, output):
        with self.store.connect() as db:
            settings = get(db, """
                SELECT e.config FROM experiments e JOIN generation_runs g ON g.experiment_id=e.id
                JOIN outputs o ON o.run_id=g.id WHERE o.id=?
            """, (output,))[0]
        return load(settings).get("triage_policy") or DEFAULT

    def refresh(self, output, policy=None, recalibrate=False):
        evaluation = self.evaluations.evaluate(output, force=recalibrate)
        with self.store.connect() as db:
            decision = latest(db, "triage_decisions", output)
        if decision and decision["evaluation_id"] == evaluation["id"] and policy is None:
            return decision
        current = policy or self.policy_for(output)
        status, reason = route(evaluation, current)
        with self.store.connect(True) as db:
            prior = latest(db, "triage_decisions", output)
            if prior and prior["status"].startswith("HUMAN_") and prior["evaluation_id"] == evaluation["id"]:
                raise Invalid("本版评测已有人工决定，重新评测后可生成新的分流")
            if prior and prior["evaluation_id"] == evaluation["id"] and prior["policy"] == dump(current):
                return prior
            return self.write_decision(db, output, evaluation["id"], status, reason, current, prior)

    @staticmethod
    def write_decision(db, output, evaluation, status, reason, policy, prior=None, reviewer=None):
        ident = uid()
        db.execute("INSERT INTO triage_decisions VALUES(?,?,?,?,?,?,?,?,?)",
                   (ident, output, evaluation, status, prior["id"] if prior else None, reviewer,
                    dump(policy), reason, now()))
        return dict(get(db, "SELECT * FROM triage_decisions WHERE id=?", (ident,)))

    def review(self, output, expected_evaluation, data):
        if not valid_scores(data["scores"]) or not data["reviewer"].strip() or not data["note"].strip():
            raise Invalid("请填写审核人、四维评分和审核理由")
        if data["source"] == "HUMAN" and not data["independent"]:
            raise Invalid("看到模型建议后的审核请选择 MODEL_ASSISTED")
        auto = self.refresh(output)
        if auto["evaluation_id"] != expected_evaluation:
            raise Invalid("评测版本已变化，请刷新后再审核")
        with self.store.connect(True) as db:
            prior = latest(db, "triage_decisions", output)
            if prior["id"] != auto["id"]:
                raise Invalid("分流已变化，请刷新后再审核")
            review = uid()
            db.execute("INSERT INTO human_reviews VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (review, output, expected_evaluation, data["reviewer"].strip(), data["source"],
                        dump(data["scores"]), data["decision"], dump(data["tags"]), data["note"].strip(), now()))
            decision = self.write_decision(db, output, expected_evaluation,
                                           "HUMAN_ACCEPT" if data["decision"] == "ACCEPT" else "HUMAN_REJECT",
                                           data["note"], load(auto["policy"]), prior, data["reviewer"].strip())
        return {"review_id": review, "triage": decision}

    def history(self, output):
        with self.store.connect() as db:
            get(db, "SELECT id FROM outputs WHERE id=?", (output,))
            return {
                "reviews": [{**dict(r), "scores": load(r["scores"]), "tags": load(r["tags"])} for r in db.execute(
                    "SELECT * FROM human_reviews WHERE output_id=? ORDER BY created_at DESC", (output,))],
                "decisions": [{**dict(r), "policy": load(r["policy"])} for r in db.execute(
                    "SELECT * FROM triage_decisions WHERE output_id=? ORDER BY created_at DESC", (output,))],
            }

    def queue(self, experiment=None):
        with self.store.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT d.*,g.experiment_id,g.task_id,g.model_config_id,g.id run_id,o.origin,o.source_id
                FROM triage_decisions d JOIN outputs o ON o.id=d.output_id JOIN generation_runs g ON g.id=o.run_id
                WHERE (? IS NULL OR g.experiment_id=?) AND d.id=(SELECT id FROM triage_decisions WHERE output_id=o.id
                       ORDER BY created_at DESC,rowid DESC LIMIT 1)
                ORDER BY (d.status='NEEDS_HUMAN_REVIEW') DESC,d.created_at DESC LIMIT 800
            """, (experiment, experiment))]

    def human_calibration(self):
        with self.store.connect() as db:
            rows = db.execute("""
                SELECT h.*,o.source_id,j.record judge FROM human_reviews h JOIN outputs o ON o.id=h.output_id
                JOIN judge_results j ON j.evaluation_id=h.evaluation_id
                WHERE h.source='HUMAN' AND o.origin!='MOCK' AND j.source='TERRA_MODEL_REFERENCE'
                  AND j.status='VALID' AND h.id=(SELECT id FROM human_reviews
                      WHERE output_id=h.output_id ORDER BY created_at DESC,rowid DESC LIMIT 1)
                ORDER BY h.created_at DESC
            """).fetchall()
        unique = {}
        for row in rows:
            unique.setdefault(row["source_id"], row)
        pairs = [(load(row["judge"])["scores"], load(row["scores"])) for row in unique.values()]
        result = compare_pairs(pairs)
        if len(pairs) < 10:
            return {"status": "INSUFFICIENT", "independent_pairs": len(pairs), "minimum": 10}
        return {"status": "AVAILABLE", "independent_pairs": len(pairs), **result}
