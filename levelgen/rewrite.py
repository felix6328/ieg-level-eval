"""「评审反馈 → 定向重写」闭环。
把 v3 清单评审里被判为有问题的题目（附原文证据）和规则层失败项，翻译成具体修改意见，
交回**同一个生成模型**做一次定向重写（多轮对话：原要求 → 原关卡 → 修改意见）。"""
from .generator import build_messages
from .llm import chat, parse_json
from .judge_v3 import VIS, EXPECT

PROBLEM = {  # 问题类题目：任一评审答 true 且给了证据即采纳（逻辑类只有带思考的评审抓得到，不能用多数票）
    "L1": "有选项的结果不是该行为的合理后果", "L2": "成败依赖场景里没铺垫的关键道具/能力/人物",
    "L3": "人物或物品的归属、空间位置前后矛盾", "L4": "result 标注与结果文字矛盾",
    "L5": "成功判定方向与场景线索相反", "L6": "目标提到场景里不存在的东西，或成功没有推进目标",
    "F4": "整体是「你来到…你需要…」式说明书模板", "D4": "内容与玩家画像硬冲突（不适龄）",
    "P3": "有明显凑数、不会有人选的选项", "P4": "存在无提示秒死或没有可推进的选项", "V1": "奖励不良价值导向"}
MISSING = {  # 加分类题目：多数评审认为没做到才采纳
    "F1": "缺少钩子：加入悬念、冲突、反转或有个性的人物", "F2": "补充至少 2 处具体、可视化的细节",
    "F3": "让至少一个结果有情绪回报或意外", "P1": "3 个选项要代表 3 种真正不同的策略",
    "P2": "场景要给出做决策的依据", "D3": "文风、信息密度、奖励类型要明显针对该玩家画像"}
RULE_FIX = {"H1_合法JSON": "必须输出合法 JSON", "H3_恰好3个选项": "必须恰好 3 个选项",
            "H6_无死局": "至少 1 个选项 result=success", "H8_结果分布符合难度": "result 分布必须符合难度定义",
            "H9_选项不同义": "3 个选项不能同义改写", "H10_儿童画像安全词": "儿童画像不能出现血腥/暴力用词"}

def feedback(v3rec, spec):
    items = [RULE_FIX.get(f, f) for f in v3rec.get("fail_list", []) if f in RULE_FIX]
    ans = {j: a for j, a in (v3rec.get("raw_answers") or {}).items() if a}
    n = max(1, len(ans))
    for q, txt in PROBLEM.items():
        hits = [(j, a.get("evidence", {}).get(q, "")) for j, a in ans.items() if a.get(q) is True]
        if hits:
            ev = next((e for _, e in hits if e), "")
            items.append(f"[{q}] {txt}" + (f"；评审引用的原文：「{str(ev)[:120]}」" if ev else ""))
    for q, txt in MISSING.items():
        if q == "D3" and spec.get("adversarial"): continue
        if sum(1 for a in ans.values() if a.get(q) is False) * 2 > n: items.append(f"[{q}] {txt}")
    exp = EXPECT[spec["difficulty"]]
    d1 = [VIS.index(a["D1"]) for a in ans.values() if a.get("D1") in VIS]
    if d1:
        m = sorted(d1)[len(d1) // 2]
        if m != exp:
            items.append(f"[D1] 关键线索的明显程度应为「{VIS[exp]}」（现在评审认为是「{VIS[m]}」），按难度调整线索")
    if spec["difficulty"] == "困难" and sum(1 for a in ans.values() if a.get("D2") is False) * 2 > n:
        items.append("[D2] 困难难度需要一个看起来合理、实际会失败的陷阱选项")
    return items

def rewrite(rec, items, model):
    msgs = build_messages(rec["spec"], "v2")
    msgs += [{"role": "assistant", "content": rec["raw"]},
             {"role": "user", "content": "关卡评审发现了以下问题，请逐条修复后输出**完整的新关卡 JSON**（格式与之前相同）。"
              "没被提到的部分尽量保留；修复逻辑问题时可以在场景里补铺垫，或改写结果。\n" +
              "\n".join(f"{k+1}. {t}" for k, t in enumerate(items)) + "\n只输出 JSON。"}]
    r = chat(model, msgs, temperature=0.7, max_tokens=1800, tag=f"rewrite:{rec['arm']}", seed_tag=f"rw:{rec['level_id']}")
    return {"level_id": rec["level_id"] + "__rw1", "arm": rec["arm"] + "+rw", "base_level_id": rec["level_id"],
            "sample": rec.get("sample", 0), "model": model, "prompt": "v2+rewrite", "spec": rec["spec"],
            "raw": r["text"], "level": parse_json(r["text"]), "feedback": items,
            "usage": {k: r[k] for k in ("prompt_tokens", "completion_tokens", "latency_s")}}
