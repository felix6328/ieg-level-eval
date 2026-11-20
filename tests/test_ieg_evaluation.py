from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase

from levelgen.ieg.evaluation import Evaluations, evidence, rules
from levelgen.ieg.experiments import Experiments, Worker
from levelgen.ieg.store import Store
from test_ieg_experiments import config


class EvaluationTest(TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "test.sqlite")
        self.exp = Experiments(self.store)
        self.evaluation = Evaluations(self.store)

    def test_terra_is_model_reference(self):
        self.assertEqual(self.evaluation.calibration()["references"], 40)
        self.assertEqual(self.evaluation.calibration()["evidence"]["terra"]["numerator"], 40)
        data = self.exp.create(config(task_ids=["cyber_easy"]))
        Worker(self.exp, self.evaluation.evaluate).one()
        result = self.evaluation.detail(self.exp.detail(data["id"])["runs"][0]["output_id"])
        self.assertEqual(len(result["rules"]), 11)
        self.assertEqual({j["source"] for j in result["judges"]}, {"HISTORICAL_JUDGE", "TERRA_MODEL_REFERENCE"})

    def test_bad_shape_and_bad_quote(self):
        failures = rules({"title": 12, "choices": [1, 2, 3]}, {"difficulty":"简单"})
        self.assertTrue(any(r["rule_id"]=="SCHEMA" and r["status"]=="FAIL" for r in failures))
        self.assertFalse(evidence("非原文", {"scene": "这是原文"}, "scene"))
