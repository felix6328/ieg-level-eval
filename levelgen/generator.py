"""关卡生成器：根据 spec（主题+难度+画像）和 prompt 版本调用生成模型。"""
import json, pathlib
from .llm import chat, parse_json
ROOT = pathlib.Path(__file__).resolve().parent.parent
P = ROOT / "prompts"

def build_messages(spec, prompt_version):
    if prompt_version == "gen_v1":
        u = (P / "gen_v1.txt").read_text().format(theme=spec["theme"], difficulty=spec["difficulty"], persona=spec["persona"])
        return [{"role": "user", "content": u}]
    sys_ = (P / "gen_v2_system.txt").read_text()
    hint = f"（元素参考：{spec['theme_hint']}）" if spec.get("theme_hint") else ""
    u = (P / "gen_v2_user.txt").read_text().format(theme=spec["theme"], theme_hint_line=hint,
        difficulty=spec["difficulty"], difficulty_def=spec["difficulty_def"],
        persona=spec["persona"], persona_desc=spec["persona_desc"])
    return [{"role": "system", "content": sys_}, {"role": "user", "content": u}]

def generate(spec, arm, model, prompt_version, temperature=0.8, sample=0):
    msgs = build_messages(spec, prompt_version)
    r = chat(model, msgs, temperature=temperature, max_tokens=1800, tag=f"gen:{arm}", seed_tag=f"{arm}:{spec['spec_id']}" + (f":s{sample}" if sample else ""))
    return {"level_id": f"{arm}__{spec['spec_id']}" + (f"__s{sample}" if sample else ""), "arm": arm, "sample": sample, "model": model, "prompt": prompt_version,
            "spec": spec, "raw": r["text"], "level": parse_json(r["text"]),
            "usage": {k: r[k] for k in ("prompt_tokens", "completion_tokens", "latency_s")}}
