"""成对比较 vs 绝对打分：在标注关卡里抽「参照总分有明显差距」的关卡对，
看成对评审 / 绝对评审推出的排序，和参照排序的一致率。输出 eval/pairwise_eval.md / .jsonl"""
import json, glob, sys, random, statistics, pathlib, itertools, concurrent.futures as cf
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from levelgen.pairwise import compare
from levelgen.systems import all_systems, DIMS
from levelgen.llm import spent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
S, offs, (ref, mp, split, src) = all_systems()
recs = {json.load(open(f))["level_id"]: json.load(open(f)) for f in glob.glob(str(ROOT / "data/levels/*.json"))}
tot = lambda s: sum(s[d] for d in DIMS)
pairs = [(a, b) for a, b in itertools.combinations(sorted(ref), 2) if abs(tot(ref[a]) - tot(ref[b])) >= 3]
random.Random(7).shuffle(pairs); pairs = pairs[:N]
def run(p):
    a, b = p
    return {"a": a, "b": b, **compare(recs[mp[a]], recs[mp[b]])}
with cf.ThreadPoolExecutor(8) as ex: R = list(ex.map(run, pairs))
with open(ROOT / "eval/pairwise_eval.jsonl", "w") as f:
    for r in R: f.write(json.dumps(r, ensure_ascii=False) + "\n")
def boot(xs, B=2000):
    rng = random.Random(0); ms = sorted(statistics.mean(rng.choices(xs, k=len(xs))) for _ in range(B))
    return ms[int(.025 * B)], ms[int(.975 * B)]
truth = {(r["a"], r["b"]): ("a" if tot(ref[r["a"]]) > tot(ref[r["b"]]) else "b") for r in R}
rows = []
pw = [1.0 if r["winner"]["overall"] == truth[(r["a"], r["b"])] else (0.5 if r["winner"]["overall"] == "tie" else 0.0) for r in R]
cons = statistics.mean(r["consistent"]["overall"] for r in R)
rows.append(("成对比较·DeepSeek-V3.2（正反序一致才算，不一致计 tie=0.5）", pw, f"{cons:.0%}"))
for name in ["v1 rubric+证据+正反序 -cal", "v3 三家族集成 -cal", "v3 清单·GLM-5.3-Flash(轻思考) -cal"]:
    sm = S[name]; xs = []
    for r in R:
        da, db = tot(sm[mp[r["a"]]]), tot(sm[mp[r["b"]]])
        w = "a" if da > db else ("b" if db > da else "tie")
        xs.append(1.0 if w == truth[(r["a"], r["b"])] else (0.5 if w == "tie" else 0.0))
    rows.append((f"绝对打分推出的排序·{name}", xs, "–"))
out = [f"# 成对比较 vs 绝对打分（{len(R)} 对，参照总分差 ≥3；参照来源：{src}）", "",
       "| 方法 | 与参照排序一致率 (95%CI) | 正反序结论一致 |", "|---|---|---|"]
for n, xs, c in rows:
    lo, hi = boot(xs); out.append(f"| {n} | {statistics.mean(xs):.0%} ({lo:.0%}~{hi:.0%}) | {c} |")
out += ["", "一致率：赢家与参照一致记 1，判 tie 记 0.5，判反记 0；随机猜的期望是 50%。"]
(ROOT / "eval/pairwise_eval.md").write_text("\n".join(out) + "\n")
print("\n".join(out)); print("累计估算花费 ¥%.3f" % spent())
