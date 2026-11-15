"""把各版本评审的结果统一成 {level_id: {维度: 分}}，供一致性、汇总、闭环脚本共用。
带 -cal 后缀的系统 = 原系统 + 每维常数偏移；偏移只用开发集（dev）上的「参照 − 评审」中位数估计。"""
import json, csv, statistics, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
DIMS = ["逻辑自洽性", "趣味性", "难度匹配度", "可玩性"]

def _jl(p):
    p = ROOT / p
    return {json.loads(l)["level_id"]: json.loads(l) for l in open(p)} if p.exists() else {}

def load_labels(path):
    out = {}
    for r in csv.DictReader(open(ROOT / path, encoding="utf-8-sig")):
        try: out[r["label_id"]] = {d: int(r[d]) for d in DIMS}
        except (ValueError, KeyError, TypeError): pass
    return out

def reference():
    """返回 (label_id→分数, label_id→level_id, label_id→split, 来源说明)。真人标注 ≥10 行时优先用真人。"""
    human = load_labels("labels/human_labels.csv")
    mp = json.load(open(ROOT / "labels/label_set_mapping.json"))
    if len(human) >= 10:
        ref, src = human, "作者人工标注（labels/human_labels.csv）"
    else:
        ref, src = load_labels("labels/provisional_reference.csv"), "⚠️ 待作者人工复核的临时标注（labels/provisional_reference.csv，Grok Bot 按 rubric 盲标，不是人工标注）"
    return ref, {m["label_id"]: m["level_id"] for m in mp}, {m["label_id"]: m.get("split", "dev") for m in mp}, src

def base_systems():
    J1, J3 = _jl("eval/judge_results.jsonl"), _jl("eval/judge_v3_results.jsonl")
    S = {}
    S["v0 无rubric单次"] = {k: v["v0"] for k, v in J1.items() if v.get("v0")}
    S["v1 rubric+证据+正反序"] = {k: v["final"] for k, v in J1.items()}
    for j, name in (("ds", "DeepSeek-V3.2"), ("glm", "GLM-5.3-Flash(轻思考)"), ("hy", "Hunyuan-A13B")):
        S[f"v3 清单·{name}"] = {k: v["per_judge"][j] for k, v in J3.items() if v["per_judge"].get(j)}
    ens = {}
    for k, v in J3.items():
        ps = [p for p in v["per_judge"].values() if p]
        if len(ps) == 3: ens[k] = {d: statistics.mean(p[d] for p in ps) for d in DIMS}
    S["v3 三家族集成"] = ens
    return S

def calibrate(sysmap, ref, mp, split):
    dev = [i for i in ref if split.get(i) == "dev" and mp[i] in sysmap]
    off = {d: statistics.median([ref[i][d] - sysmap[mp[i]][d] for i in dev]) for d in DIMS} if dev else {d: 0 for d in DIMS}
    return {k: {d: max(1, min(5, v[d] + off[d])) for d in DIMS} for k, v in sysmap.items()}, off

def all_systems(with_cal=True):
    ref, mp, split, src = reference()
    S = base_systems(); offs = {}
    if with_cal:
        for name in ["v1 rubric+证据+正反序", "v3 清单·DeepSeek-V3.2", "v3 清单·GLM-5.3-Flash(轻思考)", "v3 清单·Hunyuan-A13B", "v3 三家族集成"]:
            if S.get(name):
                S[name + " -cal"], offs[name + " -cal"] = calibrate(S[name], ref, mp, split)
    return S, offs, (ref, mp, split, src)
