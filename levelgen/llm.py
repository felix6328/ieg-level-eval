"""硅基流动 OpenAI 兼容接口的最小封装：重试、用量记录、按内容哈希缓存。"""
import hashlib, json, os, time, pathlib
import requests, yaml
from .keyloader import load_key

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = yaml.safe_load(open(ROOT / "configs/settings.yaml"))
CACHE = ROOT / "logs/cache"; CACHE.mkdir(parents=True, exist_ok=True)
USAGE = ROOT / "logs/usage.jsonl"
_KEY = None

def _key():
    global _KEY
    if _KEY is None:
        local = ROOT / ".env"   # 优先级：环境变量 > 仓库内 .env > settings.yaml 的 env_file；都只读 SILICONFLOW_API_KEY
        _KEY = os.environ.get("SILICONFLOW_API_KEY") or load_key(str(local) if local.exists() else CFG["env_file"])
    return _KEY

def cost_of(model, pin, pout):
    p = CFG["price_cny_per_m"].get(model, [0, 0])
    return (pin * p[0] + pout * p[1]) / 1e6

def spent():
    if not USAGE.exists(): return 0.0
    return sum(json.loads(l)["cost_cny"] for l in open(USAGE) if l.strip())

def chat(model, messages, temperature=0.7, max_tokens=1500, tag="", json_mode=False, seed_tag="", extra=None):
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "stream": False}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if any(k in model for k in ("DeepSeek-V3.2", "Qwen3", "GLM-5", "Hunyuan-A13B")):
        body["enable_thinking"] = False
    if extra:
        body.update(extra)
    h = hashlib.sha256(json.dumps([body, seed_tag], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
    cp = CACHE / f"{h}.json"
    if cp.exists():
        return json.load(open(cp))
    if spent() > CFG["budget_cny"]:
        raise RuntimeError("预算熔断：累计估算花费已超过 budget_cny")
    last = None
    for attempt in range(4):
        try:
            t0 = time.time()
            r = requests.post(CFG["api_base"] + "/chat/completions", json=body, timeout=180,
                              headers={"Authorization": "Bearer " + _key()})
            if r.status_code == 200:
                d = r.json(); u = d.get("usage", {})
                out = {"text": d["choices"][0]["message"].get("content") or "",
                       "prompt_tokens": u.get("prompt_tokens", 0),
                       "completion_tokens": u.get("completion_tokens", 0),
                       "latency_s": round(time.time() - t0, 2), "model": model}
                c = cost_of(model, out["prompt_tokens"], out["completion_tokens"])
                with open(USAGE, "a") as f:
                    f.write(json.dumps({"ts": time.strftime("%F %T"), "tag": tag, "model": model,
                        "pin": out["prompt_tokens"], "pout": out["completion_tokens"],
                        "latency_s": out["latency_s"], "cost_cny": round(c, 6)}, ensure_ascii=False) + "\n")
                if out["text"].strip():   # 空回复（偶发：思考后没有正文）不缓存，交给调用方重试
                    json.dump(out, open(cp, "w"), ensure_ascii=False)
                return out
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            last = repr(e)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(last)

def parse_json(text):
    """从模型输出里抠出第一个 JSON 对象；失败返回 None。"""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except Exception:
        pass
    s, e = t.find("{"), t.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(t[s:e + 1])
        except Exception:
            return None
    return None
