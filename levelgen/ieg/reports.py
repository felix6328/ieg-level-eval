"""Source-aware decision and version regression snapshots."""
from collections import defaultdict
from statistics import mean, median

from .evaluation import evidence_counts, fraction
from .governance import evaluate_assertions
from .store import ROOT, DIMS, BASE_FIELDS, Invalid, dump, get, load, now, sha, uid

HISTORICAL = {"results_v3": "results_v3.json", "triage": "triage.json", "rewrite": "rewrite_loop.json",
              "judge_agreement": "agreement.json", "retest": "retest.json"}


def average(values, source):
    return {"value": mean(values) if values else None, "denominator": len(values), "source": source}


class Reports:
    def __init__(self, store, governance):
        self.store, self.governance = store, governance
        with store.connect(True) as db:
            for name, file in HISTORICAL.items():
                if not db.execute("SELECT 1 FROM historical_reports WHERE id=?", (name,)).fetchone():
                    payload = (ROOT / "eval" / file).read_text(encoding="utf-8")
                    # Preserve original artifact even when legacy JSON contains numeric placeholders.
                    db.execute("INSERT INTO historical_reports VALUES(?,?,?)", (name,payload,f"wxg-v1.0:eval/{file}"))

    def historical(self):
        with self.store.connect() as db:
            return {r["id"]: {"source":r["source"],"data":clean(load(r["payload"]))}
                    for r in db.execute("SELECT * FROM historical_reports")}

    def list(self):
        with self.store.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,kind,created_at FROM reports ORDER BY created_at DESC")]

    def detail(self, ident):
        with self.store.connect() as db:
            row = dict(get(db,"SELECT * FROM reports WHERE id=?", (ident,)))
        return {**row, "payload":load(row["payload"]),"scope":load(row["scope"])}

    def save(self, kind, scope, payload):
        ident = uid()
        with self.store.connect(True) as db:
            db.execute("INSERT INTO reports VALUES(?,?,?,?,?)", (ident,kind,dump(scope),dump(payload),now()))
        return self.detail(ident)

    def rows(self, experiment):
        with self.store.connect() as db:
            db.execute("BEGIN")
            exp = dict(get(db,"SELECT * FROM experiments WHERE id=?", (experiment,)))
            output = []
            for row in db.execute("""
                SELECT g.*,o.id output_id,o.source_id,o.raw,a.latency,a.cost_estimate,a.response,
                       ev.id evaluation_id,ev.hard_pass,h.source reviewer_source,h.decision human_decision,
                       (SELECT d.status FROM triage_decisions d WHERE d.output_id=o.id AND d.evaluation_id=ev.id
                         AND d.reviewer IS NULL ORDER BY created_at DESC,rowid DESC LIMIT 1) automatic,
                       (SELECT d.status FROM triage_decisions d WHERE d.output_id=o.id AND d.evaluation_id=ev.id
                         ORDER BY created_at DESC,rowid DESC LIMIT 1) routed
                FROM generation_runs g
                LEFT JOIN attempts a ON a.id=(SELECT id FROM attempts WHERE run_id=g.id ORDER BY number DESC LIMIT 1)
                LEFT JOIN outputs o ON o.attempt_id=a.id
                LEFT JOIN evaluations ev ON ev.id=(SELECT id FROM evaluations WHERE output_id=o.id ORDER BY created_at DESC LIMIT 1)
                LEFT JOIN human_reviews h ON h.id=(SELECT id FROM human_reviews WHERE output_id=o.id
                  AND evaluation_id=ev.id ORDER BY created_at DESC LIMIT 1)
                WHERE g.experiment_id=? AND json_extract(g.config,'$.rewrite_for') IS NULL
                ORDER BY g.task_id,g.sample,g.model_config_id
            """, (experiment,)):
                item = dict(row)
                item["spec"] = load(row["spec"])
                item["judges"] = [load(r[0]) for r in db.execute(
                    "SELECT record FROM judge_results WHERE evaluation_id=?", (row["evaluation_id"],))]
                item["attempts"] = [dict(r) for r in db.execute("SELECT id,response,cost_estimate,latency,error FROM attempts WHERE run_id=?",
                                                              (row["id"],))]
                item["rules"] = [load(r[0]) for r in db.execute(
                    "SELECT record FROM rule_results WHERE evaluation_id=?", (row["evaluation_id"],))]
                item["rewrite"] = bool(row["output_id"] and db.execute("SELECT 1 FROM rewrites WHERE base_output=?",
                                                                      (row["output_id"],)).fetchone())
                output.append(item)
        return {**exp,"config":load(exp["config"])}, output

    def metrics(self, rows, mode):
        generated = [r for r in rows if r["status"]=="SUCCEEDED"]
        evaluated = [r for r in rows if r["evaluation_id"]]
        review = [r for r in evaluated if r["human_decision"] and mode != "MOCK"]
        accept = [r for r in review if r["human_decision"]=="ACCEPT"]
        reject = [r for r in review if r["human_decision"]=="REJECT"]
        auto_review = [r for r in review if r["automatic"]=="AUTO_PASS"]
        judges = [j for r in evaluated for j in r["judges"] if j["source"]!="TERRA_MODEL_REFERENCE"]
        terra = [j for r in evaluated for j in r["judges"] if j["source"]=="TERRA_MODEL_REFERENCE" and j["status"]=="VALID"]
        attempts = [a for r in rows for a in r["attempts"]]
        initiated = [a for a in attempts if a["response"]]
        costs = [a["cost_estimate"] for a in initiated if a["cost_estimate"] is not None]
        judge_costs = [j["cost_estimate"] for j in judges if j["source"]=="REAL_JUDGE" and j.get("cost_estimate") is not None]
        rewrites = [self.governance.rewrite_detail(r["output_id"]) for r in rows if r["rewrite"]]
        difficult = [r for r in evaluated if r["spec"]["difficulty"]=="困难" or r["spec"].get("adversarial")]
        known = [j for j in judges if j["status"]=="VALID" and j.get("scores")]
        by_output = [r for r in evaluated if r["automatic"]]
        return {
            "requests":len(rows), "generated":len(generated), "outputs":sum(bool(r["output_id"]) for r in rows),
            "evaluations":len(evaluated), "attempts":len(attempts),
            "pending":sum(r["status"] in {"PENDING","RUNNING"} for r in rows),
            "observed_at":[min((r["created_at"] for r in rows),default=None),
                           max((r["completed_at"] for r in rows if r["completed_at"]),default=None)],
            "generation_success":fraction(len(generated),len(rows)),
            "hard_pass":fraction(sum(bool(r["hard_pass"]) for r in evaluated),len(evaluated)),
            "hard_difficult":fraction(sum(bool(r["hard_pass"]) for r in difficult),len(difficult)),
            "review_rate":fraction(sum(r["automatic"]=="NEEDS_HUMAN_REVIEW" for r in by_output),len(by_output)),
            "auto_pass":fraction(sum(r["automatic"]=="AUTO_PASS" for r in by_output),len(by_output)),
            "auto_block":fraction(sum(r["automatic"]=="AUTO_BLOCK" for r in by_output),len(by_output)),
            "human_acceptance":fraction(len(accept),len(review)),
            "human_source_counts": {s:sum(r["reviewer_source"]==s for r in review) for s in ("HUMAN","MODEL_ASSISTED")},
            "human_overrides":sum(r["routed"] in {"HUMAN_REJECT","HUMAN_ACCEPT"} and
                                  (r["automatic"],r["routed"]) in {
                                      ("AUTO_PASS","HUMAN_REJECT"),("AUTO_BLOCK","HUMAN_ACCEPT")} for r in review),
            "auto_pass_precision":fraction(sum(r["human_decision"]=="ACCEPT" for r in auto_review),len(auto_review)),
            "false_pass":fraction(sum(r["automatic"]=="AUTO_PASS" for r in reject),len(reject)),
            "false_reject":fraction(sum(r["automatic"]=="AUTO_BLOCK" for r in accept),len(accept)),
            "generation_latency_s":average([r["latency"] for r in rows if r["latency"] is not None],
                                           "HISTORICAL_RECORDED" if mode=="REPLAY" else mode),
            "judge_latency_s":average([j["latency"] for j in judges if j.get("latency") is not None],"REAL_JUDGE"),
            "review_latency_s":average([],"NOT_RECORDED"),
            "estimated_generation_cost_cny":{**average(costs,"REPLAY_ZERO" if mode=="REPLAY" else mode+"_ESTIMATE"),
                                             "attempts_with_response":len(initiated),"known_total":sum(costs)},
            "estimated_judge_cost_cny": {**average(judge_costs,"REAL_ESTIMATE"), "known_total":sum(judge_costs)},
            "cost_per_human_accepted_cny":{"value":None,"denominator":len(accept),"status":"BILLING_NOT_VERIFIED"},
            "evidence_validity":evidence_counts(judges),
            "semantic":{d: average([j["scores"][d] for j in known],"VALID_JUDGE_RESULT") for d in DIMS},
            "terra_reference_subset": {d:average([j["scores"][d] for j in terra],"TERRA_MODEL_REFERENCE") for d in DIMS},
            "rewrite_success":fraction(sum(r["quality"]=="MEETS_GATE" for r in rewrites),len(rewrites)),
            "rewrite_unverified":sum(r["quality"] in {"PENDING","SEMANTIC_UNVERIFIED"} for r in rewrites),
            "key_findings":{rule:sum(1 for r in evaluated for f in r["rules"] if f["rule_id"]==rule and
                                     f["status"] in {"FAIL","WARNING"}) for rule in sorted({
                                     f["rule_id"] for r in evaluated for f in r["rules"]
                                     if f["status"] in {"FAIL","WARNING"}})},
        }

    def decision(self, experiments, hard_floor, min_evaluation):
        groups = []
        contracts = set()
        for ident in dict.fromkeys(experiments):
            exp, rows = self.rows(ident)
            contracts.add((exp["dataset_version"],exp["mode"]))
            by_group = defaultdict(list)
            for row in rows:
                by_group[row["model_config_id"]].append(row)
            for arm,group in by_group.items():
                metrics = self.metrics(group,exp["mode"])
                is_ready = metrics["pending"]==0 and metrics["evaluations"]>=min_evaluation
                eligible = is_ready and metrics["hard_pass"]["value"] >= hard_floor
                groups.append({"experiment_id":ident,"name":exp["name"],"arm":arm,"mode":exp["mode"],
                               "dataset_version":exp["dataset_version"], "config":load(group[0]["config"]),
                               "passes_structural_floor":eligible,"metrics":metrics})
        cohort_keys = {tuple(sorted((r["task_id"],r["sample"]) for r in rows if r["model_config_id"]==group["arm"]))
                       for exp_id in dict.fromkeys(experiments) for _,rows in [self.rows(exp_id)]
                       for group in groups if group["experiment_id"]==exp_id}
        comparable = len(contracts)==1 and len(cohort_keys)==1
        choices = [r for r in groups if r["passes_structural_floor"]]
        choices.sort(key=lambda r:(-r["metrics"]["hard_pass"]["value"],
                                   -r["metrics"]["generation_success"]["value"],
                                   r["metrics"]["generation_latency_s"]["value"] or 0))
        suggestion = None
        if comparable and choices and choices[0]["mode"]!="MOCK":
            item = choices[0]
            suggestion = {"arm":item["arm"],"experiment_id":item["experiment_id"],
                          "status":"STRUCTURAL_CANDIDATE","reason":"同样本范围先达到硬规则门槛，再比较结构通过率、生成成功率和延迟。",
                          "evidence":item["metrics"]["hard_pass"],"risk":"需要核实语义、真人验收和实际账单后才能作生产决策"}
        return self.save("DECISION",{"experiments":experiments,"hard_floor":hard_floor,"min_evaluation":min_evaluation},
                         {"comparable":comparable,"groups":groups,"candidate":suggestion})

    def regression(self, baseline, candidate):
        base, before = self.rows(baseline)
        current, after = self.rows(candidate)
        if base["mode"]!=current["mode"]:
            raise Invalid("回归要求相同执行模式")
        if any(r["status"] in {"PENDING","RUNNING"} for r in before+after):
            raise Invalid("请等待两个实验完成")
        indexed = {match(r):r for r in before}
        results, used = [], set()
        for row in after:
            previous = indexed.get(match(row))
            if previous:
                used.add(previous["id"])
            assertions = evaluate_assertions(row["spec"].get("assertions",[]), row, row["raw"] or "")
            if row["status"]!="SUCCEEDED" or row["evaluation_id"] is None:
                status = "CANDIDATE_FAILED"
            elif any(not a["pass"] for a in assertions):
                status = "ASSERTION_FAILED"
            elif previous is None:
                status = "UNPAIRED"
            elif previous["hard_pass"] and not row["hard_pass"]:
                status = "REGRESSION"
            elif not previous["hard_pass"] and row["hard_pass"]:
                status = "IMPROVED"
            else:
                status = "UNCHANGED"
            results.append({"task":row["task_id"],"arm":row["model_config_id"],"sample":row["sample"],
                            "before_run":previous["id"] if previous else None,"after_run":row["id"],
                            "before_hard":previous["hard_pass"] if previous else None,"after_hard":row["hard_pass"],
                            "status":status,"assertions":assertions})
        failures = {"CANDIDATE_FAILED","ASSERTION_FAILED","REGRESSION"}
        compared = [r for r in results if r["before_run"] or r["assertions"]]
        return self.save("REGRESSION",{"baseline":baseline,"candidate":candidate},
                         {"mode":base["mode"],"baseline_version":base["dataset_version"],"candidate_version":current["dataset_version"],
                          "fail_rate":fraction(sum(r["status"] in failures for r in compared),len(compared)),
                          "unpaired_candidate":sum(r["before_run"] is None for r in results),
                          "unpaired_baseline":sum(r["id"] not in used for r in before),"rows":results})


def match(row):
    spec = row["spec"]
    return (row["model_config_id"],spec.get("replay_spec_id",row["task_id"]),row["sample"],
            sha({k:spec.get(k) for k in (*BASE_FIELDS,"theme_hint")}))


def clean(value):
    import math
    if isinstance(value,float) and not math.isfinite(value):
        return None
    if isinstance(value,dict):
        return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list):
        return [clean(v) for v in value]
    return value
