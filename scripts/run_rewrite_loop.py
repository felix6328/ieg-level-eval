"""「生成 → 评审 → 定向重写 → 复评」闭环实验（B=7B、C=72B，同一 Prompt）。
1) 取该组所有不合格关卡（按 v3 三家族集成 -cal）；2) 把评审清单里的问题 + 原文证据翻译成修改意见；
3) 交回同一生成模型重写 1 次；4) 用同一评审复评；5) 再用一个**没参与出修改意见的评审形式**
（DeepSeek 成对比较，正反序）做独立复核：重写后是否真的比重写前好，以防「对着评审刷分」。
输出 data/rewrites/*.json、eval/rewrite_results.jsonl、eval/rewrite_loop.md"""
import json, glob, sys, pathlib, statistics, collections, concurrent.futures as cf
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import yaml
from levelgen.systems import all_systems, DIMS
from levelgen.rewrite import feedback, rewrite
from levelgen.judge_v3 import evaluate_v3
from levelgen.pairwise import compare
from levelgen.llm import spent
CFG = yaml.safe_load(open(ROOT / "configs/settings.yaml"))
ARMS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["B", "C"]
PW = "--no-pairwise" not in sys.argv
JUDGE = "v3 三家族集成 -cal"
S, offs, _ = all_systems(); off = offs[JUDGE]
V3 = {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / "eval/judge_v3_results.jsonl")}
recs = {json.load(open(f))["level_id"]: json.load(open(f)) for f in glob.glob(str(ROOT / "data/levels/*.json"))}
def cal(per_judge):
    ps = [p for p in per_judge.values() if p]
    if len(ps) < 3: return None
    return {d: max(1, min(5, statistics.mean(p[d] for p in ps) + off[d])) for d in DIMS}
def qual(v3r):
    s = cal(v3r["per_judge"]); return bool(s) and v3r["hard_pass"] and min(s.values()) >= 3
(ROOT / "data/rewrites").mkdir(exist_ok=True)
outp = ROOT / "eval/rewrite_results.jsonl"
done = {json.loads(l)["base_level_id"]: json.loads(l) for l in open(outp)} if outp.exists() else {}
def run(i):
    if i in done: return done[i]
    rec, v = recs[i], V3[i]
    items = feedback(v, rec["spec"])
    if not items:  # 评审没指出具体题目（只是校准后某维偏低）：针对最低维给通用意见
        low = min(DIMS, key=lambda d: cal(v["per_judge"])[d]); items = [f"「{low}」偏弱，请针对这一维度加强"]
    if rec["level"] is None:
        items = ["上次输出不是合法 JSON，请严格按格式输出"] + items
    nr = rewrite(rec, items, CFG["arms"][rec["arm"]]["model"])
    json.dump(nr, open(ROOT / f"data/rewrites/{nr['level_id']}.json", "w"), ensure_ascii=False, indent=1)
    nv = evaluate_v3(nr)
    o = {"base_level_id": i, "level_id": nr["level_id"], "arm": rec["arm"], "spec_id": rec["spec"]["spec_id"],
         "feedback": items, "before": cal(v["per_judge"]), "after": cal(nv["per_judge"]),
         "hard_pass_before": v["hard_pass"], "hard_pass_after": nv["hard_pass"], "qualified_after": qual(nv), "v3_after": nv}
    if PW and nr["level"] is not None and rec["level"] is not None:
        o["pairwise"] = compare(nr, rec, tag="rewrite")   # a = 重写后, b = 重写前
    return o
targets = sorted(i for i in recs if recs[i]["arm"] in ARMS and i in V3 and not qual(V3[i]))
print("待重写", collections.Counter(recs[i]["arm"] for i in targets))
with cf.ThreadPoolExecutor(8) as ex:
    for o in ex.map(run, targets): done[o["base_level_id"]] = o
with open(outp, "w") as f:
    for o in done.values(): f.write(json.dumps(o, ensure_ascii=False) + "\n")
print("累计估算花费 ¥%.3f" % spent())
