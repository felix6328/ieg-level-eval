"""第三批标注集（L26–L40，留出集扩充）：优化轮从 s1/s2 重复采样里抽，每组 5 关，
在评审 v3 / 成对评审 设计与运行之前盲标。抽完后留出集共 25 关。"""
import json, glob, random, pathlib, csv
ROOT = pathlib.Path(__file__).resolve().parent.parent
random.seed(26)
mp = json.load(open(ROOT / "labels/label_set_mapping.json"))
if any(m["label_id"] == "L26" for m in mp): raise SystemExit("已抽过")
used_specs = {(m["level_id"].split("__")[0], m["level_id"].split("__")[1]) for m in mp}
recs = [json.load(open(f)) for f in sorted(glob.glob(str(ROOT / "data/levels/*__s[12].json")))]
pick = []
for arm in "ABC":
    pool = [r for r in recs if r["arm"] == arm and r["level"] and (arm, r["spec"]["spec_id"]) not in used_specs]
    pick += random.sample(pool, 5)
random.shuffle(pick)
new = [{"label_id": f"L{26+i}", "level_id": r["level_id"], "split": "holdout"} for i, r in enumerate(pick)]
json.dump(mp + new, open(ROOT / "labels/label_set_mapping.json", "w"), ensure_ascii=False, indent=1)
with open(ROOT / "labels/human_labels.csv", "a", newline="") as f:
    w = csv.writer(f)
    for x in new: w.writerow([x["label_id"], "", "", "", "", "", ""])
print("\n".join(f"{x['label_id']} {x['level_id']}" for x in new))
