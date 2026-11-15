"""生成全部关卡：3 个对照组 × 24 条规格 × 3 次独立采样（s0/s1/s2）= 216 关。
s0 是第一轮的 72 关（文件名不带后缀），s1/s2 是优化轮补的重复采样，用来估计生成侧方差。"""
import json, sys, pathlib, concurrent.futures as cf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from levelgen.llm import CFG, spent
from levelgen.evalset import build_specs
from levelgen.generator import generate
OUT = pathlib.Path(__file__).resolve().parent.parent / "data/levels"

SAMPLES = (0, 1, 2)

def main(arms=None):
    specs = build_specs()
    json.dump(specs, open(OUT.parent / "eval_specs.json", "w"), ensure_ascii=False, indent=1)
    jobs = [(s, a, c, k) for a, c in CFG["arms"].items() if not arms or a in arms for s in specs for k in SAMPLES]
    def run(j):
        s, a, c, k = j
        p = OUT / (f"{a}__{s['spec_id']}" + (f"__s{k}" if k else "") + ".json")
        if p.exists(): return p.name, "skip"
        rec = generate(s, a, c["model"], c["prompt"], sample=k)
        json.dump(rec, open(p, "w"), ensure_ascii=False, indent=1)
        return p.name, "ok" if rec["level"] else "PARSE_FAIL"
    with cf.ThreadPoolExecutor(10) as ex:
        for name, st in ex.map(run, jobs):
            print(st, name)
    print(f"累计估算花费 ¥{spent():.3f}")

if __name__ == "__main__":
    main(sys.argv[1:] or None)
