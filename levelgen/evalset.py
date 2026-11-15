"""由 configs/grid.yaml 生成评测集规格。"""
import yaml, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent

def build_specs():
    g = yaml.safe_load(open(ROOT / "configs/grid.yaml"))
    diffs = list(g["difficulties"].keys())
    personas = {p["id"]: p for p in g["personas"]}
    pids = [p["id"] for p in g["personas"]]
    specs = []
    for ti, t in enumerate(g["themes"]):
        for di, d in enumerate(diffs):
            p = personas[pids[(ti + di) % len(pids)]]   # 拉丁方轮转
            specs.append({"spec_id": f"{t['id']}_{['easy','normal','hard'][di]}",
                          "theme": t["name"], "theme_hint": t["hint"], "difficulty": d,
                          "difficulty_def": g["difficulties"][d], "persona": p["name"],
                          "persona_desc": p["desc"], "persona_id": p["id"], "adversarial": False, "why": ""})
    for a in g["adversarial"]:
        p = personas[a["persona"]]
        specs.append({"spec_id": a["id"], "theme": a["theme"], "theme_hint": "", "difficulty": a["difficulty"],
                      "difficulty_def": g["difficulties"][a["difficulty"]], "persona": p["name"],
                      "persona_desc": p["desc"], "persona_id": p["id"], "adversarial": True, "why": a["why"]})
    return specs

if __name__ == "__main__":
    from collections import Counter
    s = build_specs()
    print(len(s)); print(Counter((x["difficulty"], x["persona"]) for x in s if not x["adversarial"]))
