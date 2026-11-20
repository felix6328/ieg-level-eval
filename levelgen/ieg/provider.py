"""Generation adapters. All newly billed activity requires explicit runtime enablement."""
from dataclasses import dataclass
from time import monotonic
import os

import requests

from .store import Invalid, dump, load

BUILTIN_PRICE_CNY_M = {"Qwen/Qwen2.5-7B-Instruct": (0.35, 0.35), "Qwen/Qwen2.5-72B-Instruct": (4.13, 4.13)}


@dataclass
class Reply:
    raw: str
    response: dict
    latency: float
    cost: float | None
    error: str | None = None


def parse(raw):
    raw = raw.strip()
    if raw.startswith("```") and "\n" in raw:
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return load(raw)
    except ValueError:
        return None


def render(spec, pieces):
    values = {**spec, "theme_hint_line": f"（元素参考：{spec['theme_hint']}）" if spec.get("theme_hint") else ""}
    user = {"role": "user", "content": pieces[-1].format(**values)}
    return [{"role": "system", "content": pieces[0]}, user] if len(pieces) == 2 else [user]


def config_price(model):
    configured = os.environ.get("LEVEL_EVAL_PRICES_JSON")
    prices = load(configured) if configured else {}
    pair = prices.get(model, BUILTIN_PRICE_CNY_M.get(model))
    if not pair or len(pair) != 2 or any(type(x) not in (int, float) or not 0 <= x <= 1e6 for x in pair):
        raise Invalid(f"缺少可用费用估价 {model}，请设置 LEVEL_EVAL_PRICES_JSON")
    return pair


def real_enabled():
    return os.environ.get("LEVEL_EVAL_ENABLE_REAL") == "1" and bool(
        os.environ.get("LEVEL_EVAL_API_KEY") or os.environ.get("SILICONFLOW_API_KEY")
    )


def real(body, budget, price=None):
    if not real_enabled():
        raise Invalid("REAL 需要在本机显式启用，并从环境变量配置 API 凭证")
    price_in, price_out = price if price is not None else config_price(body["model"])
    bounded_tokens = len(dump(body["messages"]).encode("utf-8")) + 256
    reserved = (bounded_tokens * price_in + body["max_tokens"] * price_out) / 1_000_000
    if reserved > budget:
        raise Invalid("剩余预算不足以执行该请求")
    url = os.environ.get("LEVEL_EVAL_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
    if not url.startswith("https://"):
        raise Invalid("REAL Provider 地址必须为 HTTPS")
    api_key = os.environ.get("LEVEL_EVAL_API_KEY") or os.environ.get("SILICONFLOW_API_KEY")
    started = monotonic()
    try:
        result = requests.post(f"{url}/chat/completions", json=body, timeout=(10, 90),
                               allow_redirects=False, headers={"Authorization": f"Bearer {api_key}"})
    except requests.RequestException as exc:
        return Reply("", {"transport_error": type(exc).__name__}, monotonic() - started, None,
                     "Provider 运输失败，可能已经收到请求")
    latency = monotonic() - started
    try:
        payload = result.json()
    except ValueError:
        payload = {"raw_http_body": result.text}
    response = {"http_status": result.status_code, "provider_response": payload}
    if result.status_code != 200:
        return Reply("", response, latency, None, f"Provider HTTP {result.status_code}")
    try:
        raw = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return Reply("", response, latency, None, "模型响应结构缺失")
    usage = payload.get("usage") or {}
    pin, pout = usage.get("prompt_tokens"), usage.get("completion_tokens")
    cost = (pin * price_in + pout * price_out) / 1_000_000 if all(type(x) is int for x in (pin, pout)) else None
    return Reply(raw if isinstance(raw, str) else "", response, latency, cost)


def mock(spec, sample):
    simple = spec["difficulty"] == "简单"
    hard = spec["difficulty"] == "困难"
    title = f"演练样本 {sample + 1}"
    scene = ("值班室里留着三份登记表。值班员说绿色标签对应直接登记，黄色标签需要先问值班员，最右侧是已经作废的旧表。"
             "墙上还有今天的值班安排，桌上只剩一盒印泥，你要决定先走哪条流程。")
    choices = [
        {"id": "A", "text": "用绿色登记表", "outcome": "保管员检查印章，你完成登记。", "result": "success",
         "next": "next_level"},
        {"id": "B", "text": "询问值班员", "outcome": "你得到新版表格，仍需复核签章。",
         "result": "fail" if hard else "partial", "next": "next_level" if simple else "retry"},
        {"id": "C", "text": "使用作废的纸张", "outcome": "柜台拒绝旧纸，请重新选择。",
         "result": "fail", "next": "retry"},
    ]
    raw = dump({"title": title, "scene": scene, "goal": "完成登记", "choices": choices})
    return Reply(raw, {"mode": "MOCK", "fixture": "registry"}, 0.0, 0.0)
