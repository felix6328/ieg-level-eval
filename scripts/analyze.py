"""【第一轮·保留作对照】72 关（每 spec 1 次采样）+ 评审 v1 / v2 / v2-cal 的汇总 → eval/results.md。
第二轮主结果见 scripts/analyze_v3.py → eval/results_v3.md。只读已有结果文件，不调用模型。"""
import json, glob, sys, pathlib, statistics, random, collections, re
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scipy.stats import spearmanr
from levelgen.checks import run_checks
DIMS = ["逻辑自洽性", "趣味性", "难度匹配度", "可玩性"]
L = lambda p: {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / p)}
J1, J2, J2c = L("eval/judge_results.jsonl"), L("eval/judge_v2_results.jsonl"), L("eval/judge_v2cal_results.jsonl")
recs = {json.load(open(f))["level_id"]: json.load(open(f)) for f in glob.glob(str(ROOT / "data/levels/*.json")) if not re.search(r"__s\d+\.json$", f)}
ARMS = json.load(open(ROOT / "eval/../configs/settings.yaml")) if False else None
import yaml; CFG = yaml.safe_load(open(ROOT / "configs/settings.yaml"))
ov = lambda s: statistics.mean(s[d] for d in DIMS)
J1 = {k: v for k, v in J1.items() if k in recs}; J2 = {k: v for k, v in J2.items() if k in recs}; J2c = {k: v for k, v in J2c.items() if k in recs}

def boot_ci(vals, n=2000, seed=1):
    r = random.Random(seed); m = []
    for _ in range(n):
        s = [r.choice(vals) for _ in vals]; m.append(statistics.mean(s))
    m.sort(); return m[int(.025 * n)], m[int(.975 * n)]

R = {}; out = ["# 实测结果汇总\n", "所有数字由 `python scripts/analyze.py` 从 `data/levels/`、`eval/*.jsonl`、`logs/usage.jsonl` 重新计算。参照标注是**待作者人工复核的临时标注**，不是人工标注。\n"]
# 1. 生成侧
out.append("## 1. 三个生成组对比（每组 24 关：18 个主题×难度网格 + 6 个对抗样例）\n")
out.append("| 组 | 配置 | 规则层通过率（阻断项） | JSON 可解析 | 评审v1 均分 | 评审v2-cal 均分 (95%CI) | 合格率（规则通过且 v2-cal 四维都≥3） | 平均生成时延 s |\n|---|---|---|---|---|---|---|---|")
for arm, c in CFG["arms"].items():
    ids = sorted(k for k in recs if recs[k]["arm"] == arm)
    hp = [J1[i]["checks"]["hard_pass"] for i in ids]
    js = [recs[i]["level"] is not None for i in ids]
    v1 = [ov(J1[i]["final"]) for i in ids]; v2 = [ov(J2c[i]["final"]) for i in ids]
    ok = [J1[i]["checks"]["hard_pass"] and min(J2c[i]["final"].values()) >= 3 for i in ids]
    lat = statistics.mean(recs[i]["usage"]["latency_s"] for i in ids)
    ci = boot_ci(v2)
    R[arm] = dict(hard_pass=sum(hp) / len(ids), json_ok=sum(js) / len(ids), v1=statistics.mean(v1), v2cal=statistics.mean(v2), v2cal_ci=ci, pass_rate=sum(ok) / len(ids), latency=lat)
    out.append(f"| {arm} | {c['model'].split('/')[-1]} + {c['prompt']}（{c['note']}） | {sum(hp)}/{len(ids)} = {sum(hp)/len(ids):.0%} | {sum(js)}/{len(ids)} | {statistics.mean(v1):.2f} | {statistics.mean(v2):.2f} ({ci[0]:.2f}–{ci[1]:.2f}) | {sum(ok)}/{len(ids)} = {sum(ok)/len(ids):.0%} | {lat:.1f} |")
out.append("\n### 1.1 规则层各检查项失败数\n")
names = list(run_checks({"title": "x", "scene": "x" * 100, "goal": "x", "choices": []}, {"difficulty": "普通", "persona_id": "kid"})["checks"].keys())
out.append("| 检查项 | " + " | ".join(CFG["arms"]) + " |\n|---|" + "---|" * len(CFG["arms"]))
cnt = collections.Counter()
for i, r in J1.items():
    for k in r["checks"]["fail_list"]: cnt[(r["arm"], k)] += 1
for k in names:
    out.append(f"| {k} | " + " | ".join(str(cnt[(a, k)]) for a in CFG["arms"]) + " |")
out.append("\n### 1.2 分维度均分（评审v2-cal）\n\n| 组 | " + " | ".join(DIMS) + " |\n|---|" + "---|" * 4)
for arm in CFG["arms"]:
    ids = [k for k in recs if recs[k]["arm"] == arm]
    out.append(f"| {arm} | " + " | ".join(f"{statistics.mean(J2c[i]['final'][d] for i in ids):.2f}" for d in DIMS) + " |")
out.append("\n### 1.3 按难度 / 对抗样例拆分（评审v2-cal 四维均分；括号内为规则层通过数/总数）\n\n| 组 | 简单 | 普通 | 困难 | 对抗样例 |\n|---|---|---|---|---|")
for arm in CFG["arms"]:
    cells = []
    for g in ("简单", "普通", "困难", "adv"):
        ids = [k for k in recs if recs[k]["arm"] == arm and ((recs[k]["spec"]["adversarial"]) if g == "adv" else (not recs[k]["spec"]["adversarial"] and recs[k]["spec"]["difficulty"] == g))]
        cells.append(f"{statistics.mean(ov(J2c[i]['final']) for i in ids):.2f} ({sum(J1[i]['checks']['hard_pass'] for i in ids)}/{len(ids)})")
    out.append(f"| {arm} | " + " | ".join(cells) + " |")
# 2. 评审偏差诊断
out.append("\n## 2. 评审偏差诊断\n")
def posbias(J, key):
    d_abs, big, signed = [], 0, []
    n = 0
    for r in J.values():
        ss = r.get(key) or []
        if len(ss) < 2: continue
        a, b = (ss[0], ss[1]) if key == "sample_scores" else (ss[0]["scores"], ss[1]["scores"])
        if any(a[d] is None or b[d] is None for d in DIMS): continue
        n += 1
        diffs = [a[d] - b[d] for d in DIMS]
        d_abs += [abs(x) for x in diffs]; signed += diffs
        big += any(abs(x) >= 2 for x in diffs)
    return n, statistics.mean(d_abs), statistics.mean(signed), big
for name, J, key in (("评审v1", J1, "sample_scores"), ("评审v2", J2, "samples")):
    n, ma, ms, big = posbias(J, key)
    R[f"posbias_{name}"] = dict(n=n, mean_abs=ma, mean_signed=ms, big=big)
    out.append(f"- **位置偏差（{name}）**：同一关卡正序 vs 倒序两次评审，{n} 关 × 4 维，平均绝对分差 {ma:.2f}，平均有符号分差（正序−倒序）{ms:+.2f}；有 {big} 关（{big/n:.0%}）至少一个维度相差 ≥2 分，这些关卡追加了第 3 次评审取中位数并进入人工抽检。")
# 篇幅偏差
lens, s1, s2 = [], [], []
for i, r in recs.items():
    if r["level"] is None: continue
    lv = r["level"]; t = len(lv.get("scene") or "") + sum(len(c.get("outcome", "")) + len(c.get("text", "")) for c in lv.get("choices", []) if isinstance(c, dict))
    lens.append(t); s1.append(ov(J1[i]["raw"])); s2.append(ov(J2c[i]["final"]))
rho1, rho2 = spearmanr(lens, s1).statistic, spearmanr(lens, s2).statistic
# 参照标注与篇幅
import csv
ref = {r["label_id"]: r for r in csv.DictReader(open(ROOT / "labels/provisional_reference.csv", encoding="utf-8-sig"))}
mp = [m for m in json.load(open(ROOT / "labels/label_set_mapping.json")) if m["level_id"] in recs]   # 第一轮的 25 个
rl, rs, j1s = [], [], []
for m in mp:
    lv = recs[m["level_id"]]["level"]
    rl.append(len(lv.get("scene") or "") + sum(len(c.get("outcome", "")) + len(c.get("text", "")) for c in lv.get("choices", []) if isinstance(c, dict)))
    rs.append(statistics.mean(int(ref[m["label_id"]][d]) for d in DIMS)); j1s.append(ov(J1[m["level_id"]]["raw"]))
rho_ref = spearmanr(rl, rs).statistic; rho_j1_sub = spearmanr(rl, j1s).statistic
R["verbosity"] = dict(rho_v1=rho1, rho_v2cal=rho2, rho_ref=rho_ref, rho_v1_labeled=rho_j1_sub, n=len(lens))
out.append(f"- **篇幅偏差**：{len(lens)} 个可解析关卡里，文本总字数与评审v1 四维均分的 Spearman ρ={rho1:.2f}，与 v2-cal ρ={rho2:.2f}。在 25 个已标注关卡上，字数与参照标注 ρ={rho_ref:.2f}，与 v1 ρ={rho_j1_sub:.2f}。注意：长度和质量本身相关（C 组更长也更好），所以 ρ>0 不等于偏差，要看「评审对长度的敏感度是否高于参照」。")
# 宽松度
for name, J, key in (("v0", J1, "v0"), ("v1", J1, "raw"), ("v2", J2, "final"), ("v2-cal", J2c, "final")):
    vals = [r[key][d] for r in J.values() if r.get(key) for d in DIMS if r[key][d] is not None]
    out.append(f"- 分数分布 {name}：均值 {statistics.mean(vals):.2f}，满分(5)占比 {sum(v >= 5 for v in vals)/len(vals):.0%}，≤2 分占比 {sum(v <= 2 for v in vals)/len(vals):.0%}（全部 72 关 × 4 维）")
lg = [J1[i]["raw"]["逻辑自洽性"] for i in J1 if recs[i]["level"] is not None]
out.append(f"- **v1 逻辑维度天花板效应**：可解析关卡中 v1 逻辑自洽性 = 5 分的比例 {sum(x >= 5 for x in lg)/len(lg):.0%}。")
# 3. 升级到人工
esc = [r for r in J1.values() if r.get("escalate")]
reasons = collections.Counter(e.split("（")[0] for r in J1.values() for e in r.get("escalate", []))
R["escalation"] = dict(rate=len(esc) / len(J1), n=len(esc), reasons=dict(reasons))
out.append(f"\n## 3. 自动 vs 人工：升级（escalation）率\n\n按 DESIGN.md §7 的升级规则，72 关中 **{len(esc)} 关（{len(esc)/len(J1):.0%}）** 会进入人工队列。触发原因计数：\n")
for k, v in reasons.most_common(): out.append(f"- {k}：{v}")
out.append(f"\n说明：对抗样例全部强制抽检（{reasons.get('对抗样例', 0)} 次计数；JSON 解析失败的关卡已被规则层直接拦截，不进评审也不进人工），所以这是偏高的上界。去掉这条规则后：")
esc2 = [r for r in J1.values() if [e for e in r.get("escalate", []) if not e.startswith("对抗样例")]]
out.append(f"- 去掉对抗样例强制抽检后：{len(esc2)}/{len(J1)} = {len(esc2)/len(J1):.0%}")
R["escalation"]["rate_no_adv"] = len(esc2) / len(J1)
# 4. 成本
use = [json.loads(l) for l in open(ROOT / "logs/usage.jsonl")]
by = collections.defaultdict(lambda: [0, 0, 0, 0.0, []])
for u in use:
    t = u["tag"].split(":")[0] if not u["tag"].startswith("gen") else u["tag"]
    b = by[t]; b[0] += 1; b[1] += u["pin"]; b[2] += u["pout"]; b[3] += u["cost_cny"]; b[4].append(u["latency_s"])
out.append("\n## 4. 调用量、成本与时延（按官网价目估算，以账单为准）\n\n| 环节 | 调用次数 | 输入 tokens | 输出 tokens | 估算花费 ¥ | 平均时延 s |\n|---|---|---|---|---|---|")
tot = 0
for t, b in sorted(by.items()):
    out.append(f"| {t} | {b[0]} | {b[1]:,} | {b[2]:,} | {b[3]:.3f} | {statistics.mean(b[4]):.1f} |"); tot += b[3]
out.append(f"| **合计** | {len(use)} | | | **{tot:.3f}** | |")
R["cost_total"] = tot
out.append(f"\n单关评审成本（v1，含正反序与必要时的第 3 次）≈ ¥{by['judge_v1'][3]/sum(1 for r in J1.values() if r.get('sample_scores')):.4f}；v2 ≈ ¥{by['judge_v2'][3]/sum(1 for r in J2.values() if r.get('samples')):.4f}。")
(ROOT / "eval/results.md").write_text("\n".join(out), encoding="utf-8")
json.dump(R, open(ROOT / "eval/results.json", "w"), ensure_ascii=False, indent=1, default=float)
print("\n".join(out))
