"""离线冒烟测试：不调用任何模型，只验证规则层、统计工具和仓库自带数据。

运行：python -m unittest discover -s tests -v
"""
import glob
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from levelgen import checks, metrics, stats  # noqa: E402


class RuleLayerTest(unittest.TestCase):
    def test_unparseable_level_is_blocked(self):
        r = checks.run_checks(None, {})
        self.assertFalse(r["hard_pass"])
        self.assertIn("H1_json可解析", r["fail_list"])

    def test_jaccard_bounds(self):
        self.assertEqual(checks.jaccard("", ""), 0)
        self.assertAlmostEqual(checks.jaccard("客栈恩怨", "客栈恩怨"), 1.0)

    def test_rule_layer_runs_on_all_stored_levels(self):
        files = sorted(glob.glob(os.path.join(ROOT, "data", "levels", "*.json")))
        self.assertEqual(len(files), 216, "仓库应保留 216 个生成关卡")
        for f in files:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            r = checks.run_checks(d.get("level"), d.get("spec") or {})
            self.assertIn("hard_pass", r)


class StatsTest(unittest.TestCase):
    def test_kappa_perfect_agreement(self):
        self.assertAlmostEqual(metrics.kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]), 1.0)

    def test_cluster_bootstrap_returns_interval(self):
        by_spec = {f"s{i}": [i % 2, 1, 0] for i in range(10)}
        out = stats.cluster_boot(by_spec, stats.flat_mean, B=200)
        self.assertTrue(out)


if __name__ == "__main__":
    unittest.main()
