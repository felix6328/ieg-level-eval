from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase

from levelgen.ieg.evaluation import Evaluations
from levelgen.ieg.experiments import Experiments, Worker
from levelgen.ieg.reviews import Reviews, route, DEFAULT
from levelgen.ieg.store import DIMS, Invalid, Store
from test_ieg_experiments import config


class ReviewTest(TestCase):
    def test_replay_has_no_fabricated_human_label_and_override_audits(self):
        with TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.sqlite")
            exp = Experiments(store)
            evaluation = Evaluations(store)
            reviews = Reviews(store, evaluation)
            result = exp.create(config(task_ids=["cyber_easy"]))
            Worker(exp, reviews.refresh).one()
            output = exp.detail(result["id"])["runs"][0]["output_id"]
            self.assertEqual(reviews.history(output)["reviews"], [])
            self.assertEqual(reviews.human_calibration()["independent_pairs"], 0)
            original = reviews.history(output)["decisions"][0]
            record = {"reviewer":"test fixture reviewer", "source":"MODEL_ASSISTED", "decision":"ACCEPT",
                      "scores":dict.fromkeys(DIMS,4), "tags":[], "note":"fixture", "independent":False}
            with self.assertRaises(Invalid):
                reviews.review(output, "stale-evaluation", record)
            reviews.review(output, original["evaluation_id"], record)
            history = reviews.history(output)
            self.assertEqual(history["decisions"][0]["prior_id"], original["id"])
            self.assertEqual(history["decisions"][0]["status"], "HUMAN_ACCEPT")
            self.assertEqual(reviews.human_calibration()["independent_pairs"], 0)

    def test_conservative_routing(self):
        valid = {"source":"REAL_JUDGE","status":"VALID","confidence":.9,"scores":dict.fromkeys(DIMS,4)}
        ev = {"rules":[], "judges":[valid,valid]}
        self.assertEqual(route(ev,DEFAULT)[0], "AUTO_PASS")
        self.assertEqual(route({**ev,"judges":[valid,{**valid,"confidence":None}]},DEFAULT)[0], "NEEDS_HUMAN_REVIEW")
        self.assertEqual(route({**ev,"rules":[{"rule_id":"H1","status":"FAIL"}]},DEFAULT)[0], "AUTO_BLOCK")
