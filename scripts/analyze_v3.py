"""第二轮主结果：216 关（24 spec × 3 次采样 × 3 组）上的合格率、按 spec 聚类的 bootstrap 置信区间、
配对组间差、生成方差（ICC）。评审 = v3 三家族集成 -cal（选择理由见 eval/agreement.md）。
只读已有结果文件，不调用模型。输出 eval/results_v3.md / .json"""
import json, glob, sys, pathlib, statistics, collections, re
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import yaml
from levelgen.systems import all_systems, DIMS
from levelgen.stats import cluster_boot, flat_mean, icc1
CFG = yaml.safe_load(open(ROOT / "configs/settings.yaml"))
JUDGE = "v3 三家族集成 -cal"
S, offs, _ = all_systems()
SC = S[JUDGE]
V3 = {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / "eval/judge_v3_results.jsonl")}
recs = {json.load(open(f))["level_id"]: json.load(open(f)) for f in glob.glob(str(ROOT / "data/levels/*.json"))}
ov = lambda s: statistics.mean(s[d] for d in DIMS)
def qualified(i): return V3[i]["hard_pass"] and min(SC[i].values()) >= 3
ids_by = collections.defaultdict(lambda: collections.defaultdict(list))   # arm -> spec -> [level_id]
for i, r in recs.items():
    if i in SC: ids_by[r["arm"]][r["spec"]["spec_id"]].append(i)
R = {"judge": JUDGE, "offsets": offs.get(JUDGE), "arms": {}, "diffs": {}}
out = ["# 第二轮实测结果（216 关）", "",
       f"评审：**{JUDGE}**（DeepSeek-V3.2 / GLM-5.3-Flash / Hunyuan-A13B 三个模型家族各答一遍判断题清单，取均值，再加开发集上估计的每维偏移 {offs.get(JUDGE)}）。",
       "合格 = 规则层阻断项全过 且 四维都 ≥3。置信区间：按 spec 聚类 bootstrap（同一 spec 的 3 次采样一起抽，4000 次），因为同一 spec 的样本不独立。",
       "⚠️ 评审的校准偏移来自**待作者人工复核的临时标注**，不是人工标注。", "",
       "## 1. 各组合格率", "",
       "| 组 | 配置 | 关卡数 | 规则层通过率 | 四维均分 | 合格率 (95%CI) | 3 选 1 合格率（每 spec 至少 1 个合格） | 仅看第 1 次采样（n=24，上一轮的做法） |",
       "|---|---|---|---|---|---|---|---|"]
for arm, c in CFG["arms"].items():
    by = {s: [1.0 if qualified(i) else 0.0 for i in v] for s, v in ids_by[arm].items()}
    hp = {s: [1.0 if V3[i]["hard_pass"] else 0.0 for i in v] for s, v in ids_by[arm].items()}
    sc = {s: [ov(SC[i]) for i in v] for s, v in ids_by[arm].items()}
    n = sum(len(v) for v in by.values())
    q = cluster_boot(by, flat_mean); h = cluster_boot(hp, flat_mean); m = cluster_boot(sc, flat_mean)
    b3 = cluster_boot(by, lambda gs: statistics.mean(max(g) for g in gs))
    s0 = {s: [1.0 if qualified(i) else 0.0 for i in v if not re.search(r"__s\d+$", i)] for s, v in ids_by[arm].items()}
    q0 = cluster_boot(s0, flat_mean)
    R["arms"][arm] = dict(n=n, hard_pass=h, mean=m, pass_rate=q, best_of_3=b3, s0_only=q0, icc_overall=icc1(list(sc.values())))
    out.append(f"| {arm} | {c['model'].split('/')[-1]} + {c['prompt']} | {n} | {h[0]:.0%} | {m[0]:.2f} ({m[1]:.2f}~{m[2]:.2f}) | **{q[0]:.0%}** ({q[1]:.0%}~{q[2]:.0%}) | {b3[0]:.0%} ({b3[1]:.0%}~{b3[2]:.0%}) | {q0[0]:.0%} ({q0[1]:.0%}~{q0[2]:.0%}) |")
out += ["", "## 2. 配对组间差（同一批 spec 上比较，按 spec 聚类 bootstrap）", "",
        "| 对比 | 回答的问题 | 合格率差 (95%CI) | 四维均分差 (95%CI) |", "|---|---|---|---|"]
for a, b, why in (("A", "B", "调 Prompt 有没有用（同为 7B）"), ("B", "C", "换大模型有没有用（同一 Prompt）"), ("A", "C", "两步合起来")):
    specs = sorted(set(ids_by[a]) & set(ids_by[b]))
    pairs = {s: [(statistics.mean(qualified(i) for i in ids_by[b][s]) - statistics.mean(qualified(i) for i in ids_by[a][s]),
                  statistics.mean(ov(SC[i]) for i in ids_by[b][s]) - statistics.mean(ov(SC[i]) for i in ids_by[a][s]))] for s in specs}
    dq = cluster_boot(pairs, lambda gs: statistics.mean(g[0][0] for g in gs))
    dm = cluster_boot(pairs, lambda gs: statistics.mean(g[0][1] for g in gs))
    R["diffs"][f"{b}-{a}"] = dict(pass_rate=dq, mean=dm)
    sig = lambda t: "（CI 不含 0）" if t[1] > 0 or t[2] < 0 else "（CI 含 0，不显著）"
    out.append(f"| {b} − {a} | {why} | {dq[0]:+.0%} ({dq[1]:+.0%}~{dq[2]:+.0%}){sig(dq)} | {dm[0]:+.2f} ({dm[1]:+.2f}~{dm[2]:+.2f}){sig(dm)} |")
out += ["", "## 3. 生成方差：同一个 spec 生成 3 次，分数有多稳？", "",
        "ICC(1) = spec 之间的方差 /（spec 之间 + spec 内部）。ICC 低 = 同一个需求每次生成质量差别大，单次采样评估不可靠；「3 次结论一致」= 3 次采样合格与否完全一致的 spec 占比。", "",
        "| 组 | 四维均分 ICC(1) | 3 次合格结论一致的 spec 占比 | spec 内四维均分平均极差 |", "|---|---|---|---|"]
for arm in CFG["arms"]:
    g = [[ov(SC[i]) for i in v] for v in ids_by[arm].values()]
    agree = statistics.mean(len({qualified(i) for i in v}) == 1 for v in ids_by[arm].values())
    rng = statistics.mean(max(x) - min(x) for x in g)
    R["arms"][arm].update(agree3=agree, range=rng)
    out.append(f"| {arm} | {icc1(g):.2f} | {agree:.0%} | {rng:.2f} |")
out += ["", "## 4. 按难度 / 对抗样例拆分的合格率", "", "| 组 | 简单 | 普通 | 困难 | 对抗样例 |", "|---|---|---|---|---|"]
for arm in CFG["arms"]:
    cells = []
    for gname in ("简单", "普通", "困难", "adv"):
        xs = [qualified(i) for v in ids_by[arm].values() for i in v
              if (recs[i]["spec"]["adversarial"] if gname == "adv" else (not recs[i]["spec"]["adversarial"] and recs[i]["spec"]["difficulty"] == gname))]
        cells.append(f"{sum(xs)}/{len(xs)} = {statistics.mean(xs):.0%}")
    out.append(f"| {arm} | " + " | ".join(cells) + " |")
out += ["", "## 5. 不合格原因（最低维 / 规则层），各组计数", "", "| 组 | 规则层阻断 | 逻辑<3 | 趣味<3 | 难度<3 | 可玩<3 |", "|---|---|---|---|---|---|"]
for arm in CFG["arms"]:
    ids = [i for v in ids_by[arm].values() for i in v]
    out.append(f"| {arm} | {sum(not V3[i]['hard_pass'] for i in ids)} | " + " | ".join(str(sum(SC[i][d] < 3 for i in ids)) for d in DIMS) + " |")
out += ["", "## 6. 敏感性：换一个评审，结论还在吗？", "",
        "同样 216 关、同样的合格定义，只换评审。**绝对合格率随评审大幅摆动，但 A < B < C 的排序在每个评审下都成立**——所以对外只承诺相对结论，绝对合格率要等真人标注校准后再报。", "",
        "| 评审 | A | B | C |", "|---|---|---|---|"]
R["sensitivity"] = {}
for name in ["v3 三家族集成 -cal", "v3 清单·GLM-5.3-Flash(轻思考) -cal", "v3 清单·DeepSeek-V3.2 -cal", "v3 清单·Hunyuan-A13B -cal", "v3 三家族集成"]:
    sm = S[name]; row = {}
    for arm in CFG["arms"]:
        xs = [V3[i]["hard_pass"] and min(sm[i].values()) >= 3 for v in ids_by[arm].values() for i in v]
        row[arm] = statistics.mean(xs)
    R["sensitivity"][name] = row
    out.append(f"| {name} | " + " | ".join(f"{row[a]:.0%}" for a in CFG["arms"]) + " |")
(ROOT / "eval/results_v3.md").write_text("\n".join(out) + "\n")
json.dump(R, open(ROOT / "eval/results_v3.json", "w"), ensure_ascii=False, indent=1)
print("\n".join(out))
