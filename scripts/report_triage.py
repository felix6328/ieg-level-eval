"""自动 vs 人工分流：三个评审家族（各自 -cal）对「合格」投票，一致则自动处理，分歧则转人工。
看：自动处理比例（216 关）、自动处理部分与参照的一致率（40 个标注关卡），人工桶里集中了多少参照错误。只读文件。"""
import json, sys, pathlib, statistics
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from levelgen.systems import all_systems, DIMS
S, offs, (ref, mp, split, src) = all_systems()
V3 = {json.loads(l)["level_id"]: json.loads(l) for l in open(ROOT / "eval/judge_v3_results.jsonl")}
J = ["v3 清单·DeepSeek-V3.2 -cal", "v3 清单·GLM-5.3-Flash(轻思考) -cal", "v3 清单·Hunyuan-A13B -cal"]
ENS = S["v3 三家族集成 -cal"]
def votes(i): return [V3[i]["hard_pass"] and min(S[j][i].values()) >= 3 for j in J]
def route(i):
    if not V3[i]["hard_pass"]: return "auto_reject"     # 规则层阻断：确定性，自动拦截
    v = votes(i)
    return "auto_pass" if all(v) else "auto_reject" if not any(v) else "human"
R = {k: sum(route(i) == k for i in V3) / len(V3) for k in ("auto_pass", "auto_reject", "human")}
out = ["# 自动 / 人工分流（三家族投票）", "",
       "规则：规则层阻断 → 自动拦截；三个评审（各自 -cal）都判合格 → 自动通过；都判不合格 → 自动拦截；有分歧 → 转人工。", "",
       f"**216 关：自动通过 {R['auto_pass']:.0%}，自动拦截 {R['auto_reject']:.0%}，转人工 {R['human']:.0%}。**", ""]
for name, ids in (("留出集 25 关", [i for i in ref if split[i] == "holdout"]), ("全部 40 个标注关卡", list(ref))):
    rq = {i: V3[mp[i]]["hard_pass"] and min(ref[i].values()) >= 3 for i in ids}
    auto = [i for i in ids if route(mp[i]) != "human"]; hum = [i for i in ids if route(mp[i]) == "human"]
    acc = statistics.mean((route(mp[i]) == "auto_pass") == rq[i] for i in auto) if auto else float("nan")
    ens_err = [i for i in ids if (V3[mp[i]]["hard_pass"] and min(ENS[mp[i]].values()) >= 3) != rq[i]]
    caught = sum(i in hum for i in ens_err)
    fp = sum(route(mp[i]) == "auto_pass" and not rq[i] for i in ids)
    out.append(f"- {name}：自动处理 {len(auto)}/{len(ids)}（{len(auto)/len(ids):.0%}），自动部分与参照一致 {acc:.0%}；"
               f"集成评审单独做门禁会判错的 {len(ens_err)} 关里，{caught} 关落在人工桶；自动通过但参照不合格（漏放）{fp} 关。")
    R[name] = dict(auto=len(auto) / len(ids), auto_acc=acc, ens_err=len(ens_err), caught=caught, false_pass=fp)
out += ["", "⚠️ 参照为待作者人工复核的临时标注。"]
(ROOT / "eval/triage.md").write_text("\n".join(out) + "\n"); json.dump(R, open(ROOT / "eval/triage.json", "w"), ensure_ascii=False, indent=1)
print("\n".join(out))
