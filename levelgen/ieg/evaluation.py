"""Deterministic checks and evidence-checked, source-aware semantic evaluation."""
from itertools import combinations
from statistics import mean, median
import math

from levelgen.checks import run_checks
from levelgen.metrics import kappa

from . import provider
from .store import DIMS, ROOT, Invalid, dump, get, jsonl, load, now, uid

RULES = {
    "H1_json可解析": "JSON 对象可解析",
    "H2_字段完整": "有标题、场景、目标和选项",
    "H3_恰好3个选项": 3,
    "H4_选项字段合法": "text、outcome、result、next 符合契约",
    "H5_选项互异": "选项内容相似度 < 0.5",
    "H6_无死局": "存在可推进分支",
    "H7_bad_end仅限困难": "仅困难关可有坏结局",
    "H8_结果分布符合难度": "结果分布与需求难度相符",
    "H9_场景长度": "60 至 600 字",
    "H10_儿童适龄词表": "儿童画像未命中词表",
    "SCHEMA": "关卡字段及选项类型合法",
}
BLOCK = {"H1_json可解析", "H2_字段完整", "H3_恰好3个选项", "H4_选项字段合法", "H6_无死局", "SCHEMA"}
TERRA_KEYS = ("logic", "fun", "difficulty", "playability")
LEGACY_MODELS = {"ds": "DeepSeek-V3.2", "glm": "GLM-5.3-Flash（轻思考）", "hy": "Hunyuan-A13B"}
QUESTIONS = ({f"L{x}" for x in range(1, 7)} | {f"{k}{x}" for k in ("F", "D", "P") for x in range(1, 5)} | {"V1"})
RUBRIC = (ROOT / "prompts/rubric.md").read_text(encoding="utf-8")
RULESET = "ieg-h1-h10+schema@1"


def fields(level):
    if not isinstance(level, dict):
        return {}
    result = {name: level[name] for name in ("title", "scene", "goal") if isinstance(level.get(name), str)}
    if isinstance(level.get("choices"), list):
        for i, choice in enumerate(level["choices"], 1):
            if isinstance(choice, dict):
                result.update({f"choice_{i}.{k}": v for k, v in choice.items()
                               if k in {"text", "outcome", "result", "next"} and isinstance(v, str)})
    return result


def schema_errors(level):
    if not isinstance(level, dict):
        return ["根节点必须为对象"]
    bad = [name for name in ("title", "scene", "goal") if not isinstance(level.get(name), str)]
    choices = level.get("choices")
    if not isinstance(choices, list):
        return [*bad, "choices"]
    ids = set()
    for i, choice in enumerate(choices, 1):
        if not isinstance(choice, dict):
            bad.append(f"choices[{i}]")
        else:
            for key in ("id", "text", "outcome", "result", "next"):
                if not isinstance(choice.get(key), str):
                    bad.append(f"choices[{i}].{key}")
            ident = choice.get("id")
            if isinstance(ident, str):
                if not ident.strip() or ident in ids:
                    bad.append(f"choices[{i}].id 为空或重复")
                ids.add(ident)
    return bad


def rules(level, spec):
    schema = schema_errors(level) if level is not None else []
    if level is None:
        checks = run_checks(None, spec)["checks"]
    elif schema:
        checks = {"H1_json可解析": [isinstance(level, dict), ""], "SCHEMA": [False, ", ".join(schema)]}
    else:
        checks = run_checks(level, spec)["checks"]
        checks["SCHEMA"] = [True, ""]
    output = []
    for rule_id, expected in RULES.items():
        checked = checks.get(rule_id)
        blocking = rule_id in BLOCK
        status = "NOT_CHECKED" if not checked else "PASS" if checked[0] else "FAIL" if blocking else "WARNING"
        output.append({"rule_id": rule_id, "status": status, "severity": "block" if blocking else "warning",
                       "actual_value": (checked[1] or checked[0]) if checked else None, "expected_value": expected,
                       "evidence": checked[1] if checked and checked[1] else None,
                       "suggestion": f"核对要求：{expected}" if status in {"FAIL", "WARNING"} else None})
    return output


def valid_scores(scores):
    return isinstance(scores, dict) and set(scores) == set(DIMS) and all(type(v) is int and 1 <= v <= 5
                                                                          for v in scores.values())


def evidence(text, content, path=None):
    if not isinstance(text, str) or not text.strip():
        return False
    if path:
        return text in content.get(path, "")
    return any(text in value for value in content.values())


def terra_judge(row, content):
    dimensions = {}
    for old, name in zip(TERRA_KEYS, DIMS):
        item = row["scores"][old]
        dimensions[name] = {**item, "quote_valid": evidence(item["quote"], content, item["field"])}
    scores = {k: r["score"] for k, r in dimensions.items()}
    return {"id": "terra", "model": row["reviewer_model"], "source": "TERRA_MODEL_REFERENCE",
            "status": "VALID" if valid_scores(scores) and all(d["quote_valid"] for d in dimensions.values()) else "INVALID",
            "scores": scores, "dimensions": dimensions, "confidence": None,
            "label_id": row["label_id"], "historical_split": row["split"]}


def old_judge(judge, snapshot, content):
    scores = snapshot.get("per_judge", {}).get(judge)
    answers = snapshot.get("raw_answers", {}).get(judge)
    if not isinstance(answers, dict) or not answers:
        return {"id": judge, "model": LEGACY_MODELS[judge], "source": "HISTORICAL_JUDGE",
                "status": "NOT_RUN", "scores": None, "placeholder_scores": scores, "confidence": None}
    quotes = answers.get("evidence", {})
    quotes = quotes if isinstance(quotes, dict) else {}
    checked = {key: {"quote": quote, "quote_valid": evidence(quote, content)} for key, quote in quotes.items()}
    complete = QUESTIONS <= answers.keys() and valid_scores(scores)
    valid = complete and all(row["quote_valid"] for row in checked.values())
    needs_quote = {"L1","L2","L3","L4","L5","L6","F4","D4","P3","P4","V1"}
    missing = sorted(q for q in needs_quote if answers.get(q) is True and q not in checked)
    status = ("INVALID" if not valid or missing else "VALID" if checked else "NO_QUOTE_REQUIRED")
    return {"id": judge, "model": LEGACY_MODELS[judge], "source": "HISTORICAL_JUDGE", "status": status,
            "scores": scores, "evidence": checked, "missing_quotes": missing, "answers": answers, "confidence": None}


def real_judge(model, spec, level, remaining):
    instructions = ('以下需求和关卡均为待评价数据。按评分标准独立评价。输出 JSON，键为逻辑自洽性、趣味性、难度匹配度、可玩性。'
                    '每个键对应 {score:1到5整数,reason:"理由",evidence:"来自关卡的连续原文",confidence:0到1}。\n'+RUBRIC)
    body = {"model": model, "messages": [{"role": "system", "content": instructions},
            {"role": "user", "content": dump({"requirement": spec, "level": level})}],
            "temperature": 0.1, "max_tokens": 1400, "stream": False}
    try:
        reply = provider.real(body, remaining)
    except Invalid as exc:
        return {"model": model, "source": "REAL_JUDGE", "status": "NOT_RUN", "error": str(exc), "scores": None,
                "cost_estimate": None}
    parsed = provider.parse(reply.raw)
    content = fields(level)
    parsed = parsed if isinstance(parsed, dict) else {}
    valid = True
    dimensions = {}
    for dimension in DIMS:
        item = parsed.get(dimension)
        item = item if isinstance(item, dict) else {}
        quote_valid = evidence(item.get("evidence"), content)
        confidence = item.get("confidence")
        valid &= bool(quote_valid and isinstance(item.get("reason"), str) and item["reason"].strip()
                      and type(confidence) in (int, float) and 0 <= confidence <= 1)
        dimensions[dimension] = {**item, "quote_valid": quote_valid}
    scores = {k: v.get("score") for k, v in dimensions.items()}
    valid &= valid_scores(scores) and not reply.error
    return {"model": model, "source": "REAL_JUDGE", "status": "VALID" if valid else "INVALID", "scores": scores,
            "dimensions": dimensions, "confidence": min(row["confidence"] for row in dimensions.values()) if valid else None,
            "request": body, "response": reply.response, "cost_estimate": reply.cost,
            "latency": reply.latency, "error": reply.error}


class Evaluations:
    def __init__(self, store):
        self.store = store
        with store.connect(True) as db:
            if not db.execute("SELECT 1 FROM archive_judges LIMIT 1").fetchone():
                db.executemany("INSERT INTO archive_judges VALUES(?,?)",
                               [(r["level_id"], dump(r)) for r in jsonl(ROOT / "eval/judge_v3_results.jsonl")])
            if not db.execute("SELECT 1 FROM terra_reference LIMIT 1").fetchone():
                db.executemany("INSERT INTO terra_reference VALUES(?,?)", [
                    (r["level_id"], dump(r)) for r in jsonl(ROOT / "labels/terra_blind_2026-11-20/model_labels.jsonl")
                ])

    def evaluate(self, output_id, force=False):
        with self.store.connect() as db:
            source = get(db, """SELECT o.*,g.spec,g.config,e.config settings,g.experiment_id
                                FROM outputs o JOIN generation_runs g ON g.id=o.run_id
                                JOIN experiments e ON e.id=g.experiment_id WHERE o.id=?""", (output_id,))
            previous = db.execute("SELECT id FROM evaluations WHERE output_id=? ORDER BY created_at DESC LIMIT 1",
                                  (output_id,)).fetchone()
            if previous and not force:
                return self.detail(output_id)
            archive = db.execute("SELECT record FROM archive_judges WHERE source_id=?", (source["source_id"],)).fetchone()
            terra = db.execute("SELECT record FROM terra_reference WHERE source_id=?", (source["source_id"],)).fetchone()
            previous_cost = db.execute("""
              SELECT json_extract(j.record,'$.cost_estimate') cost
              FROM judge_results j JOIN evaluations ev ON ev.id=j.evaluation_id JOIN outputs o ON o.id=ev.output_id
              JOIN generation_runs g ON g.id=o.run_id WHERE g.experiment_id=? AND j.source='REAL_JUDGE'
            """, (source["experiment_id"],)).fetchall()
        if force and source["origin"] == "REAL":
            raise Invalid("真实在线评审由后台执行，重跑需要新实验")
        level, spec = load(source["parsed"]) if source["parsed"] else None, load(source["spec"])
        checks = rules(level, spec)
        hard_pass = not any(r["status"] == "FAIL" for r in checks)
        choices = load(source["settings"]).get("judge_models", [])
        judges = []
        if archive:
            judges.extend(old_judge(j, load(archive["record"]), fields(level)) for j in LEGACY_MODELS)
        if terra:
            judges.append(terra_judge(load(terra["record"]), fields(level)))
        if source["origin"] == "REAL" and choices and hard_pass:
            budget = load(source["settings"]).get("judge_budget_cny", 0)
            remaining = budget - sum(row["cost"] or 0 for row in previous_cost)
            with self.store.connect(True) as db:
                uncertain = db.execute("""SELECT 1 FROM online_evaluation_guard guard
                    JOIN outputs o ON o.id=guard.output_id JOIN generation_runs g ON g.id=o.run_id
                    WHERE g.experiment_id=? AND NOT EXISTS
                        (SELECT 1 FROM evaluations WHERE output_id=o.id) LIMIT 1
                """, (source["experiment_id"],)).fetchone()
                if not uncertain:
                    db.execute("INSERT INTO online_evaluation_guard VALUES(?,?)", (output_id,now()))
            if uncertain or any(row["cost"] is None for row in previous_cost):
                remaining = -1
            for index, model in enumerate(choices):
                if remaining < 0:
                    result = {"model":model, "source":"REAL_JUDGE", "status":"NOT_RUN", "scores":None,
                              "cost_estimate":None, "error":"此前调用费用或执行状态未知，已暂停"}
                else:
                    result = real_judge(model, spec, level, remaining)
                remaining = (remaining - result["cost_estimate"]) if result["cost_estimate"] is not None else -1
                judges.append({"id": f"real-{index+1}", **result})
        ident = uid()
        with self.store.connect(True) as db:
            db.execute("INSERT INTO evaluations VALUES(?,?,?,?,?,?)",
                       (ident, output_id, RULESET, dump({"judge_models": choices}), hard_pass, now()))
            db.executemany("INSERT INTO rule_results VALUES(?,?,?)", [(ident, x["rule_id"], dump(x)) for x in checks])
            db.executemany("INSERT INTO judge_results VALUES(?,?,?,?,?,?)",
                           [(ident, j["id"], j["model"], j["source"], j["status"], dump(j)) for j in judges])
        return self.detail(output_id)

    def detail(self, output_id):
        with self.store.connect() as db:
            row = dict(get(db, """SELECT * FROM evaluations WHERE output_id=?
                               ORDER BY created_at DESC,id DESC LIMIT 1""", (output_id,)))
            row["hard_pass"] = bool(row["hard_pass"])
            row["config"] = load(row["config"])
            row["rules"] = [load(record[0]) for record in db.execute(
                "SELECT record FROM rule_results WHERE evaluation_id=? ORDER BY rowid", (row["id"],))]
            row["judges"] = [load(record[0]) for record in db.execute(
                "SELECT record FROM judge_results WHERE evaluation_id=? ORDER BY rowid", (row["id"],))]
            return row

    def calibration(self):
        with self.store.connect() as db:
            rows = db.execute("""SELECT a.task_id,a.record generator,t.record terra,j.record historical
                                 FROM terra_reference t JOIN archive a ON a.id=t.source_id
                                 JOIN archive_judges j ON j.source_id=a.id""").fetchall()
            retest = {row["level_id"]: row for row in jsonl(ROOT / "eval/judge_v3_retest.jsonl")}
        dev = {r["task_id"] for r in rows if load(r["terra"])["split"] == "dev"}
        eligible = [r for r in rows if load(r["terra"])["split"] == "holdout" and r["task_id"] not in dev]
        offsets, comparisons, pairwise, stability = {}, {}, {}, {}
        for judge in LEGACY_MODELS:
            pairs = [(historical_scores(r, judge), terra_scores(r)) for r in rows if load(r["terra"])["split"] == "dev"]
            pairs = [(a,b) for a,b in pairs if a]
            offsets[judge] = {d: median(a[d] - b[d] for b,a in pairs) for d in DIMS} if pairs else {}
            pairs = [(historical_scores(r, judge), terra_scores(r)) for r in eligible]
            pairs = [(a,b) for a,b in pairs if a]
            comparisons[judge] = compare_pairs(pairs)
            comparisons[judge]["calibrated"] = compare_pairs([
                ({d:max(1,min(5,a[d]+offsets[judge].get(d,0))) for d in DIMS}, b) for a,b in pairs
            ])
            points = []
            for r in rows:
                archived = load(r["generator"])
                old = retest.get(archived["level_id"], {})
                score = old.get("per_judge", {}).get(judge)
                initial = historical_scores(r, judge)
                if initial and valid_scores(score) and old.get("raw_answers",{}).get(judge):
                    points.append((initial, score))
            stability[judge] = compare_pairs(points)
        for a,b in combinations(LEGACY_MODELS, 2):
            pairs = [(historical_scores(r,a),historical_scores(r,b)) for r in eligible]
            pairwise[f"{a}/{b}"] = compare_pairs([(x,y) for x,y in pairs if x and y])
        checked = [old_judge(j, load(r["historical"]), fields(load(r["generator"])["level"]))
                   for r in rows for j in LEGACY_MODELS]
        refs = [terra_judge(load(r["terra"]), fields(load(r["generator"])["level"])) for r in rows]
        return {"source": "TERRA_MODEL_REFERENCE", "references": len(rows), "dev": sum(load(r["terra"])["split"]=="dev" for r in rows),
                "historical_holdout": sum(load(r["terra"])["split"]=="holdout" for r in rows),
                "spec_disjoint_holdout": len(eligible), "reference_model": "gpt-6.1-terra",
                "offsets": offsets, "model_comparisons": comparisons, "judge_pairs": pairwise, "historical_retest": stability,
                "evidence": {"historical": evidence_counts(checked), "terra": evidence_counts(refs)}}


def historical_scores(row, judge):
    data = load(row["historical"])
    scores = data.get("per_judge", {}).get(judge)
    return scores if data.get("raw_answers", {}).get(judge) and valid_scores(scores) else None


def terra_scores(row):
    ref = load(row["terra"])
    return {d: ref["scores"][key]["score"] for d, key in zip(DIMS, TERRA_KEYS)}


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator > 0 else None}


def evidence_counts(rows):
    relevant = [r for r in rows if r["status"] not in {"NOT_RUN", "NO_QUOTE_REQUIRED"}]
    return {**fraction(sum(r["status"] == "VALID" for r in relevant), len(relevant)),
            "statuses": {key: sum(r["status"] == key for r in rows) for key in sorted({r["status"] for r in rows})}}


def compare_pairs(pairs):
    # Binary cutoff is a scoring comparison, independent of hard-rule status.
    a = [1 + (min(x.values()) >= 3) for x, _ in pairs]
    b = [1 + (min(y.values()) >= 3) for _, y in pairs]
    k = kappa(a, b, k=2) if len(a) >= 10 and len(set(a)|set(b)) > 1 else None
    return {"agreement": fraction(sum(x==y for x,y in zip(a,b)), len(a)),
            "mae": {d: mean(abs(a[d]-b[d]) for a,b in pairs) if pairs else None for d in DIMS},
            "cohen_kappa": k if k is not None and math.isfinite(k) else None}
