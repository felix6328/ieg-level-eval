"""规则层硬检查：能用代码算死的，不交给模型。返回每项 pass/fail 及原因。"""
import re

RESULTS = {"success", "partial", "fail"}
NEXTS = {"next_level", "retry", "bad_end"}
KID_BANNED = ["血", "尸", "杀", "砍", "肢", "内脏", "惨叫", "死去", "鬼魂附身", "割"]

def _bigrams(s):
    s = re.sub(r"\W", "", s or "")
    return {s[i:i + 2] for i in range(len(s) - 1)}

def jaccard(a, b):
    A, B = _bigrams(a), _bigrams(b)
    return len(A & B) / max(1, len(A | B))

def run_checks(level, spec):
    """level 为解析后的 dict 或 None。返回 {check_name: (ok, detail)} 与汇总。"""
    c = {}
    if level is None:
        c["H1_json可解析"] = (False, "输出不是合法 JSON")
        return {"checks": c, "hard_pass": False, "fail_list": ["H1_json可解析"]}
    c["H1_json可解析"] = (True, "")
    miss = [k for k in ("title", "scene", "goal", "choices") if not level.get(k)]
    c["H2_字段完整"] = (not miss, "缺少 " + ",".join(miss) if miss else "")
    ch = level.get("choices") or []
    c["H3_恰好3个选项"] = (isinstance(ch, list) and len(ch) == 3, f"{len(ch) if isinstance(ch, list) else 'N/A'} 个选项")
    ch = [x for x in ch if isinstance(x, dict)] if isinstance(ch, list) else []
    bad = [x.get("id", "?") for x in ch if not (x.get("text") and x.get("outcome"))
           or x.get("result") not in RESULTS or x.get("next") not in NEXTS]
    c["H4_选项字段合法"] = (not bad, f"选项 {bad} 缺 text/outcome 或 result/next 取值非法" if bad else "")
    sims = [(ch[i].get("id"), ch[j].get("id"), jaccard(ch[i].get("text", "") + ch[i].get("outcome", ""),
             ch[j].get("text", "") + ch[j].get("outcome", ""))) for i in range(len(ch)) for j in range(i + 1, len(ch))]
    dup = [f"{a}-{b}:{s:.2f}" for a, b, s in sims if s >= 0.5]
    c["H5_选项互异"] = (not dup, "近似重复 " + ";".join(dup) if dup else "")
    res = [x.get("result") for x in ch]; nxt = [x.get("next") for x in ch]
    progress = any(r == "success" for r in res) or any(r == "partial" and n == "next_level" for r, n in zip(res, nxt))
    c["H6_无死局"] = (progress and not all(n == "bad_end" for n in nxt), "没有任何可推进的选项" if not progress else "")
    bad_end_ok = all(n != "bad_end" for n in nxt) or spec["difficulty"] == "困难"
    c["H7_bad_end仅限困难"] = (bad_end_ok, "非困难难度出现 bad_end（无提示秒死风险）" if not bad_end_ok else "")
    d = spec["difficulty"]; ns, np_, nf = res.count("success"), res.count("partial"), res.count("fail")
    if d == "简单": ok = ns + np_ >= 2; rule = "≥2 个 success/partial"
    elif d == "普通": ok = (ns, np_, nf) == (1, 1, 1); rule = "1 success/1 partial/1 fail"
    else: ok = ns == 1 and nf >= 1; rule = "恰好1 success 且 ≥1 fail"
    c["H8_结果分布符合难度"] = (ok, f"要求 {rule}，实际 s{ns}/p{np_}/f{nf}" if not ok else "")
    sl = len(level.get("scene") or "")
    c["H9_场景长度"] = (60 <= sl <= 600, f"场景 {sl} 字" if not 60 <= sl <= 600 else "")
    if spec.get("persona_id") == "kid":
        txt = (level.get("scene") or "") + "".join(x.get("outcome", "") for x in ch)
        hit = [w for w in KID_BANNED if w in txt]
        c["H10_儿童适龄词表"] = (not hit, "命中 " + ",".join(hit) if hit else "")
    fails = [k for k, (ok, _) in c.items() if not ok]
    # 阻断级：结构类问题直接判不可用；分布/长度/词表为告警，进入 LLM 评审与人工队列
    blocking = {"H1_json可解析", "H2_字段完整", "H3_恰好3个选项", "H4_选项字段合法", "H6_无死局"}
    return {"checks": {k: list(v) for k, v in c.items()}, "hard_pass": not (set(fails) & blocking), "fail_list": fails}
