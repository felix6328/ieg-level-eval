"""评测 Agent：规则层 → LLM 评审（锚定 rubric、证据先行、两次采样打乱选项顺序）→ 规则封顶 → 升级判断。"""
import json, pathlib, statistics
from .llm import chat, parse_json, CFG
from .checks import run_checks
ROOT = pathlib.Path(__file__).resolve().parent.parent
P = ROOT / "prompts"
DIMS = ["逻辑自洽性", "趣味性", "难度匹配度", "可玩性"]
RUBRIC = (P / "rubric.md").read_text()

def render_level(level, order):
    ch = level.get("choices") or []
    lines = [f"标题：{level.get('title','')}", f"场景：{level.get('scene','')}", f"目标：{level.get('goal','')}", "选项："]
    for k, i in enumerate(order):
        if i < len(ch) and isinstance(ch[i], dict):
            c = ch[i]
            lines.append(f"  选项{k+1}：{c.get('text','')}\n    结果：{c.get('outcome','')}\n    [生成器标注] result={c.get('result')} next={c.get('next')}")
    return "\n".join(lines)

def rule_facts(chk):
    bad = [f"{k}：{v[1]}" for k, v in chk["checks"].items() if not v[0]]
    return "全部通过" if not bad else "；".join(bad)

def judge_v1(rec, chk, extra=False):
    spec, level = rec["spec"], rec["level"]
    n = len(level.get("choices") or [])
    orders = [list(range(n)), list(reversed(range(n)))][:CFG["judge"]["samples"]]
    if extra:   # 两次采样分歧大时追加第 3 次（轮转顺序），取中位数
        orders = [list(range(1, n)) + [0]] if n else [[]]
    sys_ = (P / "judge_v1_system.txt").read_text().format(rubric=RUBRIC)
    samples = []
    for si, order in enumerate(orders):
        si = si + (2 if extra else 0)
        u = (f"生成要求：主题「{spec['theme']}」；难度「{spec['difficulty']}」（{spec['difficulty_def']}）；"
             f"玩家画像「{spec['persona']}」（{spec['persona_desc']}）\n规则层事实：{rule_facts(chk)}\n\n关卡：\n{render_level(level, order)}")
        r = chat(CFG["judge"]["model"], [{"role": "system", "content": sys_}, {"role": "user", "content": u}],
                 temperature=CFG["judge"]["temperature"], max_tokens=1200, tag="judge_v1", json_mode=True,
                 seed_tag=f"{rec['level_id']}:s{si}")
        j = parse_json(r["text"]) or {}
        samples.append({"order": order, "parsed": j, "latency_s": r["latency_s"]})
    if extra:
        return samples
    return samples

def judge_v0(rec):
    spec, level = rec["spec"], rec["level"]
    u = (P / "judge_v0.txt").read_text().format(theme=spec["theme"], difficulty=spec["difficulty"],
         persona=spec["persona"], level_text=render_level(level, list(range(len(level.get("choices") or [])))))
    r = chat(CFG["judge"]["model"], [{"role": "user", "content": u}], temperature=0.3, max_tokens=200,
             tag="judge_v0", json_mode=True, seed_tag=f"{rec['level_id']}:v0")
    j = parse_json(r["text"]) or {}
    return {d: j.get(d) for d in DIMS}

def _score(x):
    try:
        v = x["score"] if isinstance(x, dict) else x
        v = int(v); return v if 1 <= v <= 5 else None
    except Exception:
        return None

def evaluate(rec, with_v0=True):
    chk = run_checks(rec["level"], rec["spec"])
    out = {"level_id": rec["level_id"], "arm": rec["arm"], "spec_id": rec["spec"]["spec_id"],
           "difficulty": rec["spec"]["difficulty"], "persona": rec["spec"]["persona"],
           "adversarial": rec["spec"]["adversarial"], "checks": chk}
    if rec["level"] is None:   # 结构不可用：规则层直接判死，不花评审 token
        out.update(raw={d: 1 for d in DIMS}, final={d: 1 for d in DIMS}, sample_scores=[], tags=["F1_格式结构"],
                   v0={d: None for d in DIMS}, escalate=[], one_line="输出不是合法 JSON，规则层直接拦截")
        return out
    samples = judge_v1(rec, chk)
    ss = [{d: _score(s["parsed"].get(d)) for d in DIMS} for s in samples]
    split = [d for d in DIMS if len([s[d] for s in ss if s[d]]) == 2 and abs(ss[0][d] - ss[1][d]) >= 2]
    if split:
        samples += judge_v1(rec, chk, extra=True)
        ss = [{d: _score(s["parsed"].get(d)) for d in DIMS} for s in samples]
    raw = {}
    for d in DIMS:
        vals = [s[d] for s in ss if s[d] is not None]
        raw[d] = statistics.median(vals) if vals else None
    final = dict(raw)
    fl = set(chk["fail_list"])
    caps = []
    if fl & {"H3_恰好3个选项", "H4_选项字段合法", "H6_无死局"} and final["可玩性"] and final["可玩性"] > 2:
        final["可玩性"] = 2; caps.append("可玩性封顶2（结构/死局）")
    if "H8_结果分布符合难度" in fl and final["难度匹配度"] and final["难度匹配度"] > 3:
        final["难度匹配度"] = 3; caps.append("难度匹配度封顶3（结果分布不符）")
    tags = sorted({t for s in samples for t in (s["parsed"].get("failure_tags") or []) if isinstance(t, str)})
    if fl & {"H2_字段完整", "H3_恰好3个选项", "H4_选项字段合法"}: tags = sorted(set(tags) | {"F1_格式结构"})
    if "H6_无死局" in fl or "H7_bad_end仅限困难" in fl: tags = sorted(set(tags) | {"F8_死局秒死"})
    # 升级到人工的条件
    esc = []
    for d in DIMS:
        v = [s[d] for s in ss[:2] if s[d] is not None]
        if len(v) >= 2 and max(v) - min(v) >= 2: esc.append(f"{d} 正反序两次采样相差≥2（已追加第3次取中位数）")
        if len(v) < len(ss[:2]): esc.append(f"{d} 评审输出缺失")
    ov = statistics.mean([final[d] for d in DIMS if final[d] is not None] or [0])
    if 2.75 <= ov <= 3.25: esc.append("总分落在灰区 2.75–3.25")
    if "H10_儿童适龄词表" in fl: esc.append("儿童适龄词表命中")
    if rec["spec"]["adversarial"]: esc.append("对抗样例（抽检）")
    if "H6_无死局" in fl and (raw["可玩性"] or 0) >= 4: esc.append("规则判死局但评审给可玩性≥4（规则-评审冲突）")
    out.update(raw=raw, final=final, sample_scores=ss, orders=[s["order"] for s in samples], caps=caps, tags=tags,
               evidence={d: [s["parsed"].get(d, {}).get("evidence", "") if isinstance(s["parsed"].get(d), dict) else "" for s in samples] for d in DIMS},
               one_line=(samples[0]["parsed"].get("one_line") or ""), escalate=esc,
               v0=judge_v0(rec) if with_v0 else None)
    return out
