"""评审重测信度：同一批 40 个标注关卡，换 seed 再评一遍（eval/judge_v3_retest.jsonl），看评审跟自己的一致程度。
这是评审准确度的上限：评审连自己都对不上，就不可能和人对得上。只读文件，不调用模型。"""
import json, sys, pathlib, statistics
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scipy.stats import spearmanr
from levelgen.systems import all_systems, DIMS
from levelgen.metrics import kappa
S, offs, _ = all_systems()
A = {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / "eval/judge_v3_results.jsonl")}
B = {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / "eval/judge_v3_retest.jsonl")}
ids = sorted(B)
def ens(r):
    ps = [p for p in r["per_judge"].values() if p]
    return {d: statistics.mean(p[d] for p in ps) for d in DIMS} if len(ps) == 3 else None
off = offs["v3 三家族集成 -cal"]
q = lambda r, s: r["hard_pass"] and min(max(1, min(5, s[d] + off[d])) for d in DIMS) >= 3
out = ["# 评审重测信度（40 个标注关卡 × 换 seed 重评一次）", "",
       "| 评审 | 四维合并 ρ（第1次 vs 第2次） | 分数完全相同 | 相差 ≤1 | 二次加权κ |", "|---|---|---|---|---|"]
R = {}
for name, get in [("DeepSeek-V3.2", lambda r: r["per_judge"]["ds"]), ("GLM-5.3-Flash", lambda r: r["per_judge"]["glm"]),
                  ("Hunyuan-A13B", lambda r: r["per_judge"]["hy"]), ("三家族集成", ens)]:
    x, y = [], []
    for i in ids:
        a, b = get(A[i]), get(B[i])
        if a and b: x += [a[d] for d in DIMS]; y += [b[d] for d in DIMS]
    rho = spearmanr(x, y).statistic
    ex = statistics.mean(abs(a - b) < 1e-9 for a, b in zip(x, y)); w1 = statistics.mean(abs(a - b) <= 1 for a, b in zip(x, y))
    k = kappa([int(v) for v in x], [int(v) for v in y], weights="quadratic")
    R[name] = dict(rho=rho, exact=ex, within1=w1, qwk=k)
    out.append(f"| {name} | {rho:.2f} | {ex:.0%} | {w1:.0%} | {k:.2f} |")
agree = statistics.mean(q(A[i], ens(A[i])) == q(B[i], ens(B[i])) for i in ids)
R["qualified_decision_agreement"] = agree
out += ["", f"**合格 / 不合格结论（集成 -cal）两次一致：{agree:.0%}**（{len(ids)} 关）。", "",
        "## 逻辑类问题（L1–L6，是否判出任何逻辑问题）两次一致率", "", "| 评审 | 第1次判出 | 第2次判出 | 两次一致 |", "|---|---|---|---|"]
for j in ("ds", "glm", "hy"):
    f = lambda r: any((r.get("raw_answers", {}).get(j) or {}).get(f"L{k}") is True for k in range(1, 7))
    a = [f(A[i]) for i in ids]; b = [f(B[i]) for i in ids]
    out.append(f"| {j} | {sum(a)} | {sum(b)} | {statistics.mean(x == y for x, y in zip(a, b)):.0%} |")
(ROOT / "eval/retest.md").write_text("\n".join(out) + "\n")
json.dump(R, open(ROOT / "eval/retest.json", "w"), ensure_ascii=False, indent=1)
print("\n".join(out))
