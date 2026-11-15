"""汇总闭环实验：合格率提升、重写成功率 vs 重新采样、单个合格关卡的成本与时延。只读文件，不调用模型。"""
import json, glob, sys, pathlib, statistics, collections
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import yaml
from levelgen.systems import all_systems, DIMS
from levelgen.llm import cost_of
from levelgen.stats import cluster_boot, flat_mean
CFG = yaml.safe_load(open(ROOT / "configs/settings.yaml"))
JUDGE = "v3 三家族集成 -cal"
S, offs, _ = all_systems(); SC = S[JUDGE]
V3 = {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / "eval/judge_v3_results.jsonl")}
RW = {json.loads(l)["base_level_id"]: json.loads(l) for l in open(ROOT / "eval/rewrite_results.jsonl")}
recs = {json.load(open(f))["level_id"]: json.load(open(f)) for f in glob.glob(str(ROOT / "data/levels/*.json"))}
rws = {json.load(open(f))["base_level_id"]: json.load(open(f)) for f in glob.glob(str(ROOT / "data/rewrites/*.json"))}
U = [json.loads(l) for l in open(ROOT / "logs/usage.jsonl")]
jc = [u for u in U if u["tag"].startswith("judge_v3")]
# 每关评审成本：用全量 216 关的 v3 调用（含重试）平均，再 ×1（三个评审合计）
per_judge = collections.defaultdict(list)
for u in jc: per_judge[u["tag"]].append(u["cost_cny"])
JUDGE_COST = sum(statistics.mean(v) for v in per_judge.values())
JUDGE_LAT = max(statistics.mean(u["latency_s"] for u in jc if u["tag"] == t) for t in per_judge)  # 三家并行，取最慢
ASSUME_7B = [0.35, 0.35]   # 假设：7B 若不用免费档，按 SiliconFlow Pro 付费版标价 ¥0.35/M 估
def gcost(rec, assume=False):
    u = rec["usage"]; m = rec["model"]
    if assume and "7B" in m: return (u["prompt_tokens"] * ASSUME_7B[0] + u["completion_tokens"] * ASSUME_7B[1]) / 1e6
    return cost_of(m, u["prompt_tokens"], u["completion_tokens"])
qual0 = lambda i: V3[i]["hard_pass"] and min(SC[i].values()) >= 3
out = ["# 「评审反馈 → 定向重写」闭环实验", "",
       f"评审 = {JUDGE}；每个不合格关卡最多重写 1 次，由**同一个生成模型**完成；复评用同一评审。",
       f"每关评审成本（三家合计，实测均值，含重试）≈ ¥{JUDGE_COST:.4f}；评审时延按三家并行取最慢 ≈ {JUDGE_LAT:.0f}s。",
       "⚠️ 评审校准偏移来自待作者人工复核的临时标注。72B 单价 ¥4.13/M 为配置中的假设价；7B 在 SiliconFlow 为免费档，括号内给出按 ¥0.35/M 付费版的假设成本。", "",
       "## 1. 合格率提升", "",
       "| 组 | 关卡数 | 一次生成合格率 (95%CI) | 不合格→重写 | 重写后合格 | 重写成功率 | 对照：同 spec 重新采样一次的合格率 | 闭环后合格率 (95%CI) | 提升 |",
       "|---|---|---|---|---|---|---|---|---|"]
R = {}
for arm in sorted({r["arm"] for r in RW.values()}):
    ids = [i for i in recs if recs[i]["arm"] == arm and i in SC]
    fails = [i for i in ids if not qual0(i)]
    ok_rw = [i for i in fails if i in RW and RW[i]["qualified_after"]]
    by0 = collections.defaultdict(list); by1 = collections.defaultdict(list)
    for i in ids:
        s = recs[i]["spec"]["spec_id"]; by0[s].append(float(qual0(i))); by1[s].append(float(qual0(i) or (i in RW and RW[i]["qualified_after"])))
    q0, q1 = cluster_boot(by0, flat_mean), cluster_boot(by1, flat_mean)
    # 对照：一个不合格关卡如果不重写、而是同 spec 重新生成一次，合格概率 = 同 spec 其他样本的合格率
    resample = statistics.mean(statistics.mean(qual0(j) for j in ids if recs[j]["spec"]["spec_id"] == recs[i]["spec"]["spec_id"] and j != i) for i in fails)
    rr = len(ok_rw) / len(fails) if fails else float("nan")
    # 成本
    g = statistics.mean(gcost(recs[i]) for i in ids); ga = statistics.mean(gcost(recs[i], True) for i in ids)
    rwc = [gcost(rws[i]) for i in fails if i in rws]; rwa = [gcost(rws[i], True) for i in fails if i in rws]
    lat_g = statistics.mean(recs[i]["usage"]["latency_s"] for i in ids)
    lat_rw = statistics.mean(rws[i]["usage"]["latency_s"] for i in fails if i in rws)
    n, Q0, Q1 = len(ids), sum(qual0(i) for i in ids), sum(qual0(i) for i in ids) + len(ok_rw)
    c0 = n * (g + JUDGE_COST) / Q0; c1 = (n * (g + JUDGE_COST) + len(fails) * (statistics.mean(rwc) + JUDGE_COST)) / Q1
    a0 = n * (ga + JUDGE_COST) / Q0; a1 = (n * (ga + JUDGE_COST) + len(fails) * (statistics.mean(rwa) + JUDGE_COST)) / Q1
    t0 = n * (lat_g + JUDGE_LAT) / Q0; t1 = (n * (lat_g + JUDGE_LAT) + len(fails) * (lat_rw + JUDGE_LAT)) / Q1
    R[arm] = dict(n=n, q0=q0, q1=q1, fails=len(fails), ok_rw=len(ok_rw), rewrite_success=rr, resample=resample,
                  cost0=c0, cost1=c1, cost0_assumed=a0, cost1_assumed=a1, sec0=t0, sec1=t1, gen_cost=g, rw_cost=statistics.mean(rwc))
    out.append(f"| {arm}（{recs[ids[0]]['model'].split('/')[-1]}） | {n} | {q0[0]:.0%} ({q0[1]:.0%}~{q0[2]:.0%}) | {len(fails)} | {len(ok_rw)} | {rr:.0%} | {resample:.0%} | {q1[0]:.0%} ({q1[1]:.0%}~{q1[2]:.0%}) | {q1[0]-q0[0]:+.0%} |")
out += ["", "## 2. 单个合格关卡的成本与时延（生成 + 评审 + 重写 + 复评，全部摊到合格关卡上）", "",
        "| 组 | 每关生成成本 | 每次重写成本 | ¥/合格关卡·一次生成 | ¥/合格关卡·闭环 | 串行耗时 s/合格关卡·一次生成 | 闭环 |", "|---|---|---|---|---|---|---|"]
for arm, r in R.items():
    tag = "（7B 免费档；括号内为假设付费价）" if arm in ("A", "B") else ""
    f = lambda x, y: f"¥{x:.4f}" + (f"（¥{y:.4f}）" if arm in ("A", "B") else "")
    out.append(f"| {arm}{tag} | ¥{r['gen_cost']:.4f} | ¥{r['rw_cost']:.4f} | {f(r['cost0'], r['cost0_assumed'])} | {f(r['cost1'], r['cost1_assumed'])} | {r['sec0']:.0f} | {r['sec1']:.0f} |")
# 3. 重写前后分维度 + 独立成对复核
out += ["", "## 3. 重写改了什么：被重写关卡的分维度均分（重写前 → 重写后）", "", "| 组 | " + " | ".join(DIMS) + " | 规则层通过 |", "|---|---|---|---|---|---|"]
for arm in R:
    xs = [r for r in RW.values() if r["arm"] == arm and r["after"] and r["before"]]
    out.append(f"| {arm} | " + " | ".join(f"{statistics.mean(r['before'][d] for r in xs):.2f} → {statistics.mean(r['after'][d] for r in xs):.2f}" for d in DIMS)
               + f" | {sum(r['hard_pass_before'] for r in xs)}/{len(xs)} → {sum(r['hard_pass_after'] for r in xs)}/{len(xs)} |")
out += ["", "## 4. 独立复核：换一种评审形式（DeepSeek 成对比较，正反两个顺序都认为同一方更好才算）", "",
        "目的：排除「重写只是学会了讨好清单评审」。成对比较不看清单、不看分数，只问两版哪个更好。", "",
        "| 组 | 对数 | 重写后更好 | 打平/顺序不一致 | 重写前更好 | 逻辑维：重写后更好 / 更差 |", "|---|---|---|---|---|---|"]
for arm in R:
    xs = [r["pairwise"] for r in RW.values() if r["arm"] == arm and r.get("pairwise")]
    if not xs: continue
    c = collections.Counter(x["winner"]["overall"] for x in xs); cl = collections.Counter(x["winner"]["逻辑自洽性"] for x in xs)
    out.append(f"| {arm} | {len(xs)} | {c['a']} ({c['a']/len(xs):.0%}) | {c['tie']} | {c['b']} ({c['b']/len(xs):.0%}) | {cl['a']} / {cl['b']} |")
    R[arm]["pairwise"] = dict(c)
(ROOT / "eval/rewrite_loop.md").write_text("\n".join(out) + "\n")
json.dump(R, open(ROOT / "eval/rewrite_loop.json", "w"), ensure_ascii=False, indent=1)
print("\n".join(out))
