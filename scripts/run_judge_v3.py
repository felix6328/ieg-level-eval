"""评审 v3（三家族集成）。用法：
  python scripts/run_judge_v3.py labeled          # 只跑 40 个标注关卡（先评估再决定是否全量）
  python scripts/run_judge_v3.py all [ds,glm,hy]  # 全部 216 关
  python scripts/run_judge_v3.py retest           # 标注关卡重测（不同 seed，测评审自身一致性）
结果追加/覆盖到 eval/judge_v3_results.jsonl（retest 写 eval/judge_v3_retest.jsonl）。"""
import json, glob, sys, pathlib, concurrent.futures as cf
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from levelgen.judge_v3 import evaluate_v3
from levelgen.llm import spent
mode = sys.argv[1] if len(sys.argv) > 1 else "labeled"
judges = tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 else ("ds", "glm", "hy")
recs = {json.load(open(f))["level_id"]: json.load(open(f)) for f in sorted(glob.glob(str(ROOT / "data/levels/*.json")))}
labeled = [m["level_id"] for m in json.load(open(ROOT / "labels/label_set_mapping.json"))]
ids = list(recs) if mode == "all" else labeled
outp = ROOT / ("eval/judge_v3_retest.jsonl" if mode == "retest" else "eval/judge_v3_results.jsonl")
old = {json.loads(l)["level_id"]: json.loads(l) for l in open(outp)} if outp.exists() else {}
def run(lid):
    return evaluate_v3(recs[lid], judges, retest=1 if mode == "retest" else 0)
def save():
    with open(outp, "w") as f:
        for r in old.values(): f.write(json.dumps(r, ensure_ascii=False) + "\n")
with cf.ThreadPoolExecutor(10) as ex:
    for n, fut in enumerate(cf.as_completed([ex.submit(run, i) for i in ids]), 1):
        r = fut.result()
        prev = old.get(r["level_id"])
        if prev:  # 合并不同评审的结果
            prev["per_judge"].update(r["per_judge"]); prev.setdefault("raw_answers", {}).update(r.get("raw_answers", {})); r = prev
        old[r["level_id"]] = r
        if n % 20 == 0: save(); print(n, "/", len(ids), flush=True)
save()
print(len(ids), "judged v3", judges, "累计估算花费 ¥%.3f" % spent())
