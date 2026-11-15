"""评审 v2：「找茬式清单」——LLM 只回答判断题/列问题，分数由程序按固定公式合成。
动机：v1（rubric+证据先行）在参照集上明显偏宽松（逻辑自洽性 65% 给满分），证据环节变成了「为高分找理由」。"""
import json, pathlib, statistics
from .llm import chat, parse_json, CFG
from .checks import run_checks
from .judge import render_level, rule_facts, DIMS
ROOT = pathlib.Path(__file__).resolve().parent.parent
SYS = (ROOT / "prompts/judge_v2_system.txt").read_text()
VIS = ["明显", "需要阅读", "隐蔽但可回溯", "无线索"]
EXPECT = {"简单": 0, "普通": 1, "困难": 2}

def clip(x): return max(1, min(5, int(round(x))))

def synth(a, difficulty):
    """把清单回答合成为 1–5 分。公式即评分口径，改公式要重跑一致性。"""
    iss = a.get("logic_issues") or []
    major = sum(1 for i in iss if isinstance(i, dict) and i.get("severity") == "major")
    minor = sum(1 for i in iss if isinstance(i, dict) and i.get("severity") != "major")
    logic = clip(5 - 1.5 * major - 0.5 * minor - (1 if a.get("goal_scene_mismatch") else 0))
    det = a.get("concrete_details", 0)
    try: det = int(str(det).rstrip("+"))
    except Exception: det = 0
    fun = clip(2 + (1 if a.get("has_hook") else 0) + (1 if det >= 2 else 0) + (1 if a.get("outcome_payoff") else 0)
               - (1 if a.get("template_opening") else 0))
    vis = a.get("clue_visibility", "无线索"); vi = VIS.index(vis) if vis in VIS else 3
    exp = EXPECT.get(difficulty, 1)
    dist = (1 if exp == 0 else 2) if vi == 3 else abs(vi - exp)
    diff = 5 - dist - (1 if difficulty == "困难" and not a.get("has_trap") else 0)
    pf = a.get("persona_fit", "一般")
    diff -= {"明显针对": 0, "一般": 1, "未体现": 2}.get(pf, 0)
    diff = clip(diff)
    if pf.startswith("冲突"): diff = min(diff, 2)
    try: ds = int(a.get("distinct_strategies", 3))
    except Exception: ds = 3
    try: fo = int(a.get("filler_options", 0))
    except Exception: fo = 0
    play = 2 + ds - (0 if a.get("decision_basis") else 1) - min(fo, 1)
    play = clip(play)
    if a.get("dead_end"): play = min(play, 2)
    return {"逻辑自洽性": logic, "趣味性": fun, "难度匹配度": diff, "可玩性": play}

def evaluate_v2(rec):
    chk = run_checks(rec["level"], rec["spec"])
    base = {"level_id": rec["level_id"]}
    if rec["level"] is None:
        return {**base, "raw": {d: 1 for d in DIMS}, "final": {d: 1 for d in DIMS}, "samples": [], "tags": ["F1_格式结构"]}
    spec, level = rec["spec"], rec["level"]
    n = len(level.get("choices") or [])
    orders = [list(range(n)), list(reversed(range(n)))]
    def one(si, order):
        u = (f"生成要求：主题「{spec['theme']}」；难度「{spec['difficulty']}」（{spec['difficulty_def']}）；"
             f"玩家画像「{spec['persona']}」（{spec['persona_desc']}）\n规则层事实：{rule_facts(chk)}\n\n关卡：\n{render_level(level, order)}")
        r = chat(CFG["judge"]["model"], [{"role": "system", "content": SYS}, {"role": "user", "content": u}],
                 temperature=CFG["judge"]["temperature"], max_tokens=1200, tag="judge_v2", json_mode=True,
                 seed_tag=f"{rec['level_id']}:v2s{si}")
        a = parse_json(r["text"]) or {}
        return {"order": order, "answers": a, "scores": synth(a, spec["difficulty"])}
    samples = [one(i, o) for i, o in enumerate(orders)]
    if any(abs(samples[0]["scores"][d] - samples[1]["scores"][d]) >= 2 for d in DIMS):
        samples.append(one(2, list(range(1, n)) + [0]))
    raw = {d: statistics.median([s["scores"][d] for s in samples]) for d in DIMS}
    final = dict(raw); fl = set(chk["fail_list"])
    if fl & {"H3_恰好3个选项", "H4_选项字段合法", "H6_无死局"}: final["可玩性"] = min(final["可玩性"], 2)
    if "H8_结果分布符合难度" in fl: final["难度匹配度"] = min(final["难度匹配度"], 3)
    tags = sorted({t for s in samples for t in (s["answers"].get("failure_tags") or []) if isinstance(t, str)})
    return {**base, "raw": raw, "final": final, "samples": samples, "tags": tags,
            "logic_issues": samples[0]["answers"].get("logic_issues", []), "one_line": samples[0]["answers"].get("one_line", "")}
