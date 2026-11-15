"""对优化轮新增的标注关卡（L26–L40）补跑评审 v0/v1，用于和 v3 同场对比。结果合并进 eval/judge_results.jsonl。"""
import json, sys, pathlib, concurrent.futures as cf
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from levelgen.judge import evaluate
from levelgen.llm import spent
J = {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / "eval/judge_results.jsonl")}
need = [m["level_id"] for m in json.load(open(ROOT / "labels/label_set_mapping.json")) if m["level_id"] not in J]
with cf.ThreadPoolExecutor(8) as ex:
    for r in ex.map(lambda lid: evaluate(json.load(open(ROOT / f"data/levels/{lid}.json"))), need): J[r["level_id"]] = r
with open(ROOT / "eval/judge_results.jsonl", "w") as f:
    for r in J.values(): f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(need), "v1 补跑；累计 ¥%.3f" % spent())
