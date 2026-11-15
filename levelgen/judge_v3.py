"""评审 v3：分解式判断题清单（19 道是非/单选题）+ 多家族评审集成。

与 v2 的区别：
- 不让模型判断严重度（v2 的严重度膨胀），每道题只答是/否，并要求原文证据；
- 把「生成要求自带张力」单列为 spec_tension，不计入扣分（v2 的画像冲突误判）；
- 分数公式**事先固定**，不在标注集上搜索权重，只允许每维一个常数偏移校准；
- 3 个不同家族的模型各评一次，各用不同的选项顺序（正序/倒序/轮转），用集成同时平均掉位置偏差与单模型偏好。
"""
import json, pathlib, statistics
from .llm import chat, parse_json
from .checks import run_checks
from .judge import render_level, rule_facts, DIMS
ROOT = pathlib.Path(__file__).resolve().parent.parent
SYS = (ROOT / "prompts/judge_v3_system.txt").read_text()
VIS = ["明显", "需要阅读", "隐蔽但可回溯", "无线索"]
EXPECT = {"简单": 0, "普通": 1, "困难": 2}
JUDGES = {  # 名称: (模型, 顺序方案)
    "ds":  ("deepseek-ai/DeepSeek-V3.2", "fwd"),
    "glm": ("zai-org/GLM-5.3-Flash", "rev"),   # 唯一开了轻量思考（thinking_budget=1024）的评审
    "hy":  ("tencent/Hunyuan-A13B-Instruct", "rot"),
}

def _b(a, k):
    v = a.get(k)
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "是", "yes"))

def synth(a, difficulty):
    """事先固定的合成公式（不在标注集上调参）。"""
    logic = 5 - sum(_b(a, f"L{i}") for i in range(1, 7))
    fun = 1 + _b(a, "F1") + _b(a, "F2") + _b(a, "F3") + (not _b(a, "F4"))
    vis = a.get("D1", "无线索"); vi = VIS.index(vis) if vis in VIS else 3
    exp = EXPECT.get(difficulty, 1)
    dist = (1 if exp == 0 else 2) if vi == 3 else abs(vi - exp)
    diff = 5 - dist - (1 if difficulty == "困难" and not _b(a, "D2") else 0) - (0 if _b(a, "D3") else 1)
    if _b(a, "D4"): diff = min(diff, 2)
    play = 2 + _b(a, "P1") + _b(a, "P2") + (not _b(a, "P3"))
    if _b(a, "P4"): play = min(play, 2)
    c = lambda x: max(1, min(5, x))
    return {"逻辑自洽性": c(logic), "趣味性": c(fun), "难度匹配度": c(diff), "可玩性": c(play)}

def _order(scheme, n):
    if scheme == "rev": return list(reversed(range(n)))
    if scheme == "rot": return list(range(1, n)) + [0] if n else []
    return list(range(n))

def judge_one(rec, name, chk=None, retest=0):
    model, scheme = JUDGES[name]
    spec, level = rec["spec"], rec["level"]
    chk = chk or run_checks(level, spec)
    order = _order(scheme, len(level.get("choices") or []))
    u = (f"生成要求：主题「{spec['theme']}」；难度「{spec['difficulty']}」（{spec['difficulty_def']}）；"
         f"玩家画像「{spec['persona']}」（{spec['persona_desc']}）\n规则层事实：{rule_facts(chk)}\n\n关卡：\n{render_level(level, order)}")
    for attempt in range(3):   # 偶发空回复或缺字段时重试（重试改 seed 以绕过缓存，并关闭 json_mode）
        r = chat(model, [{"role": "system", "content": SYS}, {"role": "user", "content": u}], temperature=0.3,
                 max_tokens=2500 if name == "glm" else 1200, tag=f"judge_v3:{name}", json_mode=(attempt == 0),
                 extra={"enable_thinking": True, "thinking_budget": 1024} if name == "glm" else None,
                 seed_tag=f"{rec['level_id']}:v3:{name}" + (f":rt{retest}" if retest else "") + (f":try{attempt}" if attempt else ""))
        a = parse_json(r["text"]) or {}
        ok = all(k in a for k in ("L1", "F1", "D1", "P1"))
        if ok: break
    return {"judge": name, "order": order, "answers": a, "valid": ok,
            "scores": synth(a, spec["difficulty"]) if ok else None, "latency_s": r["latency_s"]}

def caps(scores, chk):
    s = dict(scores); fl = set(chk["fail_list"])
    if fl & {"H3_恰好3个选项", "H4_选项字段合法", "H6_无死局"}: s["可玩性"] = min(s["可玩性"], 2)
    if "H8_结果分布符合难度" in fl: s["难度匹配度"] = min(s["难度匹配度"], 3)
    return s

def evaluate_v3(rec, judges=("ds", "glm", "hy"), retest=0):
    chk = run_checks(rec["level"], rec["spec"])
    out = {"level_id": rec["level_id"], "arm": rec["arm"], "spec_id": rec["spec"]["spec_id"],
           "sample": rec.get("sample", 0), "hard_pass": chk["hard_pass"], "fail_list": chk["fail_list"], "per_judge": {}}
    if rec["level"] is None:
        out["per_judge"] = {j: {d: 1 for d in DIMS} for j in judges}; out["raw_answers"] = {}
        return out
    ans = {}
    for j in judges:
        r = judge_one(rec, j, chk, retest)
        ans[j] = r["answers"]
        out["per_judge"][j] = caps(r["scores"], chk) if r["valid"] else None
    out["raw_answers"] = ans
    return out
