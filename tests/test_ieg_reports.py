from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase

from levelgen.ieg.evaluation import Evaluations
from levelgen.ieg.experiments import Experiments, Worker
from levelgen.ieg.reviews import Reviews
from levelgen.ieg.governance import Governance
from levelgen.ieg.reports import Reports
from levelgen.ieg.store import Store
from test_ieg_experiments import config


class ReportTest(TestCase):
    def test_full_history_replay_and_decision_denominators(self):
        with TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/"ieg.sqlite")
            exp = Experiments(store)
            ev = Evaluations(store)
            rv = Reviews(store,ev)
            report = Reports(store,Governance(store,exp,ev,rv))
            replay = exp.create(config(models=["A","B","C"],repeats=3))
            worker = Worker(exp,rv.refresh)
            while worker.one():
                pass
            out = report.decision([replay["id"]],.8,70)["payload"]
            self.assertEqual(sum(x["metrics"]["requests"] for x in out["groups"]),216)
            self.assertEqual(sum(x["metrics"]["generated"] for x in out["groups"]),212)
            self.assertEqual(sum(x["metrics"]["evaluations"] for x in out["groups"]),216)
            self.assertEqual(sum(x["metrics"]["terra_reference_subset"]["逻辑自洽性"]["denominator"] for x in out["groups"]),40)
            self.assertEqual(out["candidate"]["arm"], "C")
            self.assertTrue(all(x["metrics"]["human_acceptance"]["value"] is None for x in out["groups"]))
            one = exp.create(config(task_ids=["cyber_easy"]))
            worker.one()
            regression = report.regression(replay["id"],one["id"])["payload"]
            self.assertEqual(regression["fail_rate"]["denominator"],1)
            self.assertEqual(regression["unpaired_baseline"],215)
