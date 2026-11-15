"""自动评测 vs 参照标注 的一致性（开发集 / 留出集 / 全部），并与常数基线对比。
参照：labels/human_labels.csv 有 ≥10 行完整分数时用真人，否则用「待作者人工复核的临时标注」。
输出：eval/agreement.md 与 eval/agreement.json。"""
import json, sys, pathlib, statistics
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from levelgen.metrics import agreement, bootstrap_spearman
from levelgen.systems import all_systems, DIMS

def main():
    S, offs, (ref, mp, split, src) = all_systems()
    dev_ids = [i for i in ref if split.get(i) == "dev"]
    const = {d: statistics.median([ref[i][d] for i in dev_ids]) for d in DIMS}
    S = {"常数基线（永远猜开发集中位数）": {mp[i]: const for i in ref}, **S}
    out = {"reference": src, "offsets": offs, "const": const, "splits": {}}
    L = ["# 自动评测 vs 参照标注 一致性\n", f"**参照来源：{src}**\n",
         "- 开发集 dev = L01–L15：第一轮评审迭代时看过它的错误；所有 `-cal` 偏移只在这 15 关上估计。",
         "- 留出集 holdout = L16–L40（25 关）：L16–L25 在第一轮 v2 设计前盲标；L26–L40 在优化轮从重复采样中抽取，在 v3 设计和运行前盲标。**看结论以留出集为准。**",
         "- 「四维合并」把 4 个维度的分数拼在一起算（n = 关卡数 × 4）；ρ 的 95% CI 为 bootstrap。",
         "- 任何评审的 MAE 都应明显低于常数基线，否则只是在往均值猜。\n"]
    for sp_name, cond in (("holdout", lambda i: split.get(i) == "holdout"), ("dev", lambda i: split.get(i) == "dev"), ("all", lambda i: True)):
        ids = [i for i in sorted(ref) if cond(i)]
        L.append(f"\n## {'留出集' if sp_name=='holdout' else '开发集' if sp_name=='dev' else '全部'}（{len(ids)} 关）\n")
        L.append("| 评审 | 覆盖 | 四维合并 ρ (95%CI) | 二次加权κ | MAE | 精确一致 | 逻辑 ρ | 趣味 ρ | 难度 ρ | 可玩 ρ |\n|---|---|---|---|---|---|---|---|---|---|")
        out["splits"][sp_name] = {}
        for name, sm in S.items():
            have = [i for i in ids if mp[i] in sm]
            if len(have) < 5: continue
            P = [sm[mp[i]][d] for i in have for d in DIMS]; R = [ref[i][d] for i in have for d in DIMS]
            pooled = agreement(P, R); ci = bootstrap_spearman(P, R)
            per = {d: agreement([sm[mp[i]][d] for i in have], [ref[i][d] for i in have]) for d in DIMS}
            fmt = lambda m: "–" if m is None or m["spearman"] != m["spearman"] else f"{m['spearman']:.2f}"
            L.append(f"| {name} | {len(have)} | {pooled['spearman']:.2f} ({ci[0]:.2f}~{ci[1]:.2f}) | {pooled['qwk']:.2f} | {pooled['mae']:.2f} | {pooled['exact']:.0%} | " + " | ".join(fmt(per[d]) for d in DIMS) + " |")
            out["splits"][sp_name][name] = {"n": len(have), "pooled": pooled, "ci": ci, "per_dim": per}
    # 业务上真正用到的是「合格 / 不合格」二分判定：看误放（不合格被放过）和误杀（合格被拦下）
    HP = {json.loads(l)["level_id"]: json.loads(l)["hard_pass"] for l in open(ROOT / "eval/judge_v3_results.jsonl")}
    L.append("\n## 合格判定（规则层通过 且 四维都 ≥3）与参照的一致性\n")
    L.append("参照的合格 = 规则层通过 且 参照四维都 ≥3。误放率 = 参照不合格里被判合格的比例；误杀率 = 参照合格里被判不合格的比例。\n")
    for sp_name, cond in (("留出集", lambda i: split.get(i) == "holdout"), ("全部 40 关", lambda i: True)):
        ids = [i for i in sorted(ref) if cond(i)]
        rq = {i: HP[mp[i]] and min(ref[i].values()) >= 3 for i in ids}
        L.append(f"\n### {sp_name}（参照合格 {sum(rq.values())} / {len(ids)}）\n\n| 评审 | 判定一致率 | 误放率 | 误杀率 |\n|---|---|---|---|")
        out["splits"].setdefault("gate", {})[sp_name] = {}
        for name, sm in S.items():
            if not all(mp[i] in sm for i in ids): continue
            pq = {i: HP[mp[i]] and min(sm[mp[i]].values()) >= 3 for i in ids}
            neg = [i for i in ids if not rq[i]]; pos = [i for i in ids if rq[i]]
            acc = statistics.mean(pq[i] == rq[i] for i in ids)
            fp = statistics.mean(pq[i] for i in neg) if neg else float("nan"); fn = statistics.mean(not pq[i] for i in pos) if pos else float("nan")
            L.append(f"| {name} | {acc:.0%} | {fp:.0%}（{sum(pq[i] for i in neg)}/{len(neg)}） | {fn:.0%}（{sum(not pq[i] for i in pos)}/{len(pos)}） |")
            out["splits"]["gate"][sp_name][name] = {"acc": acc, "false_pass": fp, "false_reject": fn}
    sd = {d: statistics.pstdev([ref[i][d] for i in ref]) for d in DIMS}
    L.append("\n参照分数的离散度（标准差）：" + "，".join(f"{d} {sd[d]:.2f}" for d in DIMS) + "。参照几乎都落在 3–4 分，所以「永远猜中位数」的 MAE 天然很低；排序类指标（ρ、κ）和合格判定更能说明评审有没有用。")
    L.append(f"\n偏移校准量（参照 − 评审，开发集中位数）：")
    for k, v in offs.items(): L.append(f"- {k}：" + "，".join(f"{d} {v[d]:+g}" for d in DIMS))
    (ROOT / "eval/agreement.md").write_text("\n".join(L), encoding="utf-8")
    json.dump(out, open(ROOT / "eval/agreement.json", "w"), ensure_ascii=False, indent=1, default=float)
    print("\n".join(L))

if __name__ == "__main__":
    main()
