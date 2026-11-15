"""评审 v2 公式校准（不再调用模型）：只用开发集 L01–L15 网格搜索合成公式的权重，最小化 MAE，
然后原样应用到全部关卡；留出集 L16–L25 不参与搜索，用来检验。结果写 eval/judge_v2cal_results.jsonl。"""
import json, csv, sys, pathlib, itertools, statistics
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from levelgen.judge_v2 import VIS, EXPECT
from levelgen.checks import run_checks
DIMS = ["逻辑自洽性", "趣味性", "难度匹配度", "可玩性"]
clip = lambda x: max(1, min(5, int(round(x))))

def feats(a, spec):
    iss = [i for i in (a.get("logic_issues") or []) if isinstance(i, dict)]
    pf = str(a.get("persona_fit", "一般"))
    if pf.startswith("冲突") and spec["persona_id"] != "kid": pf = "一般"   # 只有儿童画像才可能「冲突」（适龄）；其余视为误用
    try: det = int(str(a.get("concrete_details", 0)).rstrip("+"))
    except Exception: det = 0
    vis = a.get("clue_visibility", "无线索")
    try: ds = int(a.get("distinct_strategies", 3))
    except Exception: ds = 3
    try: fo = int(a.get("filler_options", 0))
    except Exception: fo = 0
    return dict(major=sum(i.get("severity") == "major" for i in iss), minor=sum(i.get("severity") != "major" for i in iss),
                gm=bool(a.get("goal_scene_mismatch")), hook=bool(a.get("has_hook")), det=det, pay=bool(a.get("outcome_payoff")),
                tmpl=bool(a.get("template_opening")), vi=VIS.index(vis) if vis in VIS else 3, trap=bool(a.get("has_trap")),
                pf=pf, ds=ds, basis=bool(a.get("decision_basis")), fo=fo, dead=bool(a.get("dead_end")))

def score(f, spec, w):
    logic = clip(w["L0"] - w["LM"] * f["major"] - w["Lm"] * f["minor"] - (0.5 if f["gm"] else 0))
    fun = clip(w["F0"] + f["hook"] + (f["det"] >= 2) + f["pay"] - f["tmpl"])
    exp = EXPECT.get(spec["difficulty"], 1)
    dist = (1 if exp == 0 else 2) if f["vi"] == 3 else abs(f["vi"] - exp)
    d = 5 - w["Dd"] * dist - (1 if spec["difficulty"] == "困难" and not f["trap"] else 0) - {"明显针对": 0, "一般": w["Dp"], "未体现": 2 * w["Dp"]}.get(f["pf"], 0)
    d = clip(d)
    if f["pf"].startswith("冲突"): d = min(d, 2)
    play = clip(w["P0"] + f["ds"] - (0 if f["basis"] else w["Pb"]) - min(f["fo"], 1))
    if f["dead"]: play = min(play, 2)
    return {"逻辑自洽性": logic, "趣味性": fun, "难度匹配度": d, "可玩性": play}

def final_scores(rec, j2, w):
    if rec["level"] is None: return {d: 1 for d in DIMS}
    per = [score(feats(s["answers"], rec["spec"]), rec["spec"], w) for s in j2["samples"]]
    out = {d: statistics.median([p[d] for p in per]) for d in DIMS}
    fl = set(run_checks(rec["level"], rec["spec"])["fail_list"])
    if fl & {"H3_恰好3个选项", "H4_选项字段合法", "H6_无死局"}: out["可玩性"] = min(out["可玩性"], 2)
    if "H8_结果分布符合难度" in fl: out["难度匹配度"] = min(out["难度匹配度"], 3)
    return out

def main():
    J2 = {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / "eval/judge_v2_results.jsonl")}
    recs = {lid: json.load(open(ROOT / f"data/levels/{lid}.json")) for lid in J2}
    def load(p):
        out = {}
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            try: out[r["label_id"]] = {d: int(r[d]) for d in DIMS}
            except (ValueError, KeyError, TypeError): pass
        return out
    ref = load(ROOT / "labels/human_labels.csv")
    if len(ref) < 10:   # 真人标注不足时退回临时标注
        ref = load(ROOT / "labels/provisional_reference.csv")
    mp = json.load(open(ROOT / "labels/label_set_mapping.json"))
    dev = [(m["level_id"], ref[m["label_id"]]) for m in mp if m["split"] == "dev" and m["label_id"] in ref]
    grid = dict(L0=[4, 4.5, 5], LM=[0.5, 0.75, 1.0, 1.5], Lm=[0, 0.25, 0.5], F0=[1, 1.5, 2], Dd=[0.5, 1], Dp=[0, 0.5, 1], P0=[1, 1.5, 2], Pb=[0, 1])
    keys = list(grid); best = None
    for vals in itertools.product(*[grid[k] for k in keys]):
        w = dict(zip(keys, vals))
        err = sum(abs(final_scores(recs[lid], J2[lid], w)[d] - r[d]) for lid, r in dev for d in DIMS)
        if best is None or err < best[0]: best = (err, w)
    w = best[1]
    print("开发集最优权重：", w, " 开发集 MAE=%.3f" % (best[0] / (4 * len(dev))))
    json.dump({"weights": w, "dev_mae": best[0] / (4 * len(dev)), "grid": grid}, open(ROOT / "eval/v2_calibration.json", "w"), ensure_ascii=False, indent=1)
    with open(ROOT / "eval/judge_v2cal_results.jsonl", "w") as f:
        for lid in J2:
            f.write(json.dumps({"level_id": lid, "final": final_scores(recs[lid], J2[lid], w)}, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
