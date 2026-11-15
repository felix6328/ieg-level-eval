"""第二批标注集（L16–L25，留出集）：在评审 v2 设计之前抽取并盲标，用来检验 v2 改动是否只是拟合了第一批。"""
import json, glob, random, pathlib, csv
ROOT = pathlib.Path(__file__).resolve().parent.parent
random.seed(7)
used = {m["level_id"] for m in json.load(open(ROOT / "labels/label_set_mapping.json"))}
recs = [json.load(open(f)) for f in sorted(glob.glob(str(ROOT / "data/levels/*.json")))]
pick = []
for arm, k in (("A", 3), ("B", 4), ("C", 3)):
    pool = [r for r in recs if r["arm"] == arm and r["level"] and r["level_id"] not in used]
    pick += random.sample(pool, k)
random.shuffle(pick)
m = [{"label_id": f"L{16+i}", "level_id": r["level_id"], "split": "holdout"} for i, r in enumerate(pick)]
allm = json.load(open(ROOT / "labels/label_set_mapping.json"))
for x in allm: x.setdefault("split", "dev")
allm += m
json.dump(allm, open(ROOT / "labels/label_set_mapping.json", "w"), ensure_ascii=False, indent=1)
with open(ROOT / "labels/human_labels.csv", "a", newline="") as f:
    w = csv.writer(f)
    for x in m: w.writerow([x["label_id"], "", "", "", "", "", ""])
print("\n".join(f"{x['label_id']} {x['level_id']}" for x in m))
