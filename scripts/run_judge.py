"""对全部关卡跑评测 Agent，结果写入 eval/judge_results.jsonl。"""
import json, glob, sys, pathlib, concurrent.futures as cf
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from levelgen.judge import evaluate
from levelgen.llm import spent
recs = [json.load(open(f)) for f in sorted(glob.glob(str(ROOT / "data/levels/*.json")))]
with cf.ThreadPoolExecutor(6) as ex:
    res = list(ex.map(evaluate, recs))
with open(ROOT / "eval/judge_results.jsonl", "w") as f:
    for r in res: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(res), "judged; 累计估算花费 ¥%.3f" % spent())
