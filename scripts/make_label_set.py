"""抽取人工标注集：每个对照组 5 关（只从 JSON 可解析的关卡里抽），按难度/对抗样例分层，
匿名化为 L01..L15（标注者看不到模型和 prompt 版本），随机打乱顺序。"""
import json, glob, random, sys, pathlib, csv
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
random.seed(20261115)
recs = [json.load(open(f)) for f in sorted(glob.glob(str(ROOT / "data/levels/*.json")))]
pick = []
for arm in "ABC":
    pool = [r for r in recs if r["arm"] == arm and r["level"]]
    by = lambda cond: [r for r in pool if cond(r)]
    groups = [by(lambda r: not r["spec"]["adversarial"] and r["spec"]["difficulty"] == d) for d in ("简单", "普通", "困难")]
    chosen = [random.choice(g) for g in groups]
    adv = [r for r in by(lambda r: r["spec"]["adversarial"])]
    chosen += random.sample(adv, 1)
    rest = [r for r in pool if r not in chosen and not r["spec"]["adversarial"]]
    chosen += random.sample(rest, 1)
    pick += chosen
# 每个规格最多出现在两个组里也没关系；打乱后匿名
random.shuffle(pick)
mapping = [{"label_id": f"L{i+1:02d}", "level_id": r["level_id"]} for i, r in enumerate(pick)]
json.dump(mapping, open(ROOT / "labels/label_set_mapping.json", "w"), ensure_ascii=False, indent=1)
DIMS = ["逻辑自洽性", "趣味性", "难度匹配度", "可玩性"]
with open(ROOT / "labels/human_labels.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["label_id", *DIMS, "标注人", "备注"])
    for m in mapping: w.writerow([m["label_id"], "", "", "", "", "", ""])
print("\n".join(f"{m['label_id']} {m['level_id']}" for m in mapping))
