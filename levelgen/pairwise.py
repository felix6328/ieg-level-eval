"""成对比较评审：同时给两个关卡，问哪个更好（四维 + 总体）。每对正反两个顺序各问一次，
两次结论一致才算有效判断，不一致记为 tie（位置偏差的直接度量）。"""
import pathlib
from .llm import chat, parse_json
from .judge import render_level, DIMS
ROOT = pathlib.Path(__file__).resolve().parent.parent
SYS = (ROOT / "prompts/pairwise_system.txt").read_text()
MODEL = "deepseek-ai/DeepSeek-V3.2"

def _block(rec, k):
    s = rec["spec"]; lv = rec["level"]
    return (f"【关卡 {k}】生成要求：主题「{s['theme']}」；难度「{s['difficulty']}」（{s['difficulty_def']}）；"
            f"画像「{s['persona']}」（{s['persona_desc']}）\n{render_level(lv, list(range(len(lv.get('choices') or []))))}")

def ask(r1, r2, tag):
    u = _block(r1, 1) + "\n\n" + _block(r2, 2)
    r = chat(MODEL, [{"role": "system", "content": SYS}, {"role": "user", "content": u}], temperature=0.0,
             max_tokens=300, tag=f"pairwise:{tag}", json_mode=True, seed_tag=f"pw:{r1['level_id']}|{r2['level_id']}")
    return parse_json(r["text"]) or {}

def compare(ra, rb, tag="eval"):
    """返回每个维度与 overall 的胜者：'a' / 'b' / 'tie'，以及两次顺序是否一致。"""
    x, y = ask(ra, rb, tag), ask(rb, ra, tag)
    res, consistent = {}, {}
    for k in DIMS + ["overall"]:
        v1 = {"1": "a", "2": "b"}.get(str(x.get(k)), "tie")
        v2 = {"1": "b", "2": "a"}.get(str(y.get(k)), "tie")
        res[k] = v1 if v1 == v2 else "tie"
        consistent[k] = v1 == v2
    return {"winner": res, "consistent": consistent, "raw": [x, y]}
