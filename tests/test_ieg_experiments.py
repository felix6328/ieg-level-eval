import tempfile
import unittest
from pathlib import Path

from levelgen.ieg.experiments import Experiments, Worker
from levelgen.ieg.store import Invalid, Store


def config(**params):
    return {"name": "Replay", "dataset_version": "wxg24-v1", "mode": "REPLAY", "models": ["A"],
            "repeats": 1, "seed": 0, "task_ids": [], "temperature": None, "max_tokens": None,
            "model_override": None, "prompt_override": None, "budget_cny": 0, **params}


class ExperimentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "ieg.sqlite")
        self.exp = Experiments(self.store)
        self.worker = Worker(self.exp)

    def test_archive_is_idempotent(self):
        Store(self.store.path)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM archive").fetchone()[0], 216)
        self.assertEqual(len(self.store.tasks("wxg24-v1")), 24)

    def test_frozen_version_and_snapshot(self):
        spec = {**self.store.tasks("wxg24-v1")[0], "theme": "修改后的输入"}
        draft = self.store.version(dataset_id="wxg24", name="", tasks=[spec], note="test")
        with self.assertRaises(Invalid):
            self.exp.create(config(dataset_version=draft["id"]))
        self.store.freeze(draft["id"])
        created = self.exp.create(config(dataset_version=draft["id"]))
        self.worker.one()
        run, = self.exp.detail(created["id"])["runs"]
        self.assertEqual(run["status"], "FAILED")
        self.assertIn("不一致", run["error"])

    def test_replay_keeps_failed_output_and_attempts(self):
        item = self.exp.create(config(task_ids=["wuxia_easy", "cyber_easy"]))
        while self.worker.one():
            pass
        data = self.exp.detail(item["id"])
        self.assertEqual({r["status"] for r in data["runs"]}, {"SUCCEEDED", "FAILED"})
        bad = next(r for r in data["runs"] if r["status"] == "FAILED")
        self.assertEqual(bad["origin"], "REPLAY")
        self.exp.retry(bad["id"])
        self.assertTrue(self.worker.one())
        self.assertEqual(len(self.exp.run_detail(bad["id"])["attempts"]), 2)
