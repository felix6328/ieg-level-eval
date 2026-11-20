from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase

from levelgen.ieg.evaluation import Evaluations
from levelgen.ieg.experiments import Experiments, Worker
from levelgen.ieg.reviews import Reviews
from levelgen.ieg.governance import Governance
from levelgen.ieg.store import Invalid, Store
from test_ieg_experiments import config


class GovernanceTest(TestCase):
    def test_replay_rewrite_and_golden_version(self):
        with TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.sqlite")
            exp = Experiments(store)
            engine = Evaluations(store)
            reviews = Reviews(store,engine)
            gov = Governance(store,exp,engine,reviews)
            worker = Worker(exp,reviews.refresh)
            parent = exp.create(config(models=["B"],task_ids=["adv_hard_casual"]))
            worker.one()
            output = exp.detail(parent["id"])["runs"][0]["output_id"]
            bad = gov.create_bad(output,"Unknown","fixture","")
            self.assertFalse(bad["confirmed"])
            candidate = gov.create_golden(bad["id"],"Fixture candidate",{},[{"type":"hard_pass"}])
            with self.assertRaises(Invalid):
                gov.golden_action(candidate["id"],"publish","fixture","premature")
            gov.golden_action(candidate["id"],"validate","","")
            gov.golden_action(candidate["id"],"approve","Test fixture reviewer","test only")
            active = gov.golden_action(candidate["id"],"publish","Test fixture reviewer","test only")
            self.assertEqual(len(store.tasks(active["dataset_version"])),1)
            exp.create(config(dataset_version=active["dataset_version"],models=["B"]))
            worker.one()
            self.assertTrue(gov.rewrite(output,"核对困难关的选择与线索")["run_id"])
            with self.assertRaises(Invalid):
                gov.rewrite(output,"重复")
            worker.one()
            result = gov.rewrite_detail(output)
            self.assertEqual(result["run"]["status"],"SUCCEEDED")
            self.assertTrue(result["recorded_historical"])
            self.assertIsNotNone(result["after"])
            gov.golden_action(candidate["id"],"deprecate","Test fixture reviewer","test only")
            self.assertEqual(len(store.tasks(active["dataset_version"])),1)
