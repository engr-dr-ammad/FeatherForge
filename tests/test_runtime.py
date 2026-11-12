import tempfile
import unittest
from pathlib import Path
from forge.store import Store
from forge.runtime import Runtime
from forge.providers import ScriptedProvider


class PassingRunner:
    image = "test double (NOT real isolation)"

    def run(self, t, workspace, active):
        return {
            "passed": True,
            "simulated": True,
            "output": "orchestration-only test double",
        }

    def cancel(self, t):
        pass


class FailingRunner(PassingRunner):
    def run(self, *args):
        return {"passed": False, "simulated": True, "output": "intentional failure"}


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.runtime = Runtime(self.store, PassingRunner())
        self.runtime.call_model = (
            lambda t, p, role, objective, context: ScriptedProvider().call(
                role, objective, context
            )
        )
        self.pid = self.store.create(
            "Tracker",
            "Build accessible task tracker with persistence",
            "scripted",
            "test-key-123",
        )
        self.runtime.plan(self.pid)

    def tearDown(self):
        self.runtime.pool.shutdown()
        self.tmp.cleanup()

    def run_next(self):
        t = self.runtime.claim()
        self.assertIsNotNone(t)
        self.runtime.execute(t)
        return t

    def test_approval_and_complete_evidence(self):
        self.assertIsNone(self.runtime.claim())
        self.runtime.approve(self.pid)
        for _ in range(3):
            self.run_next()
        tasks = self.store.project(self.pid)["tasks"]
        self.assertEqual([t["state"] for t in tasks], ["completed"] * 3)
        self.assertTrue(all(t["workspace"] and t["artifacts"] for t in tasks))
        self.assertTrue(tasks[1]["evidence"][0]["passed"])

    def test_restart_and_ownership(self):
        self.runtime.approve(self.pid)
        self.run_next()
        qa = self.runtime.claim()
        recovered = Store(self.tmp.name)
        recovered.recover()
        self.assertEqual(recovered.task(qa["id"])["state"], "blocked")
        build = recovered.project(self.pid)["tasks"][0]
        self.assertEqual(build["state"], "review")
        self.assertTrue(Path(build["workspace"], "index.html").is_file())
        self.assertEqual(recovered.task(qa["id"])["role"], "qa")

    def test_failed_checks_gate_completion(self):
        self.runtime.runner = FailingRunner()
        self.runtime.approve(self.pid)
        self.run_next()
        qa = self.run_next()
        self.assertEqual(self.store.task(qa["id"])["state"], "failed")
        self.assertIsNone(self.runtime.claim())
        self.assertEqual(self.store.project(self.pid)["tasks"][0]["state"], "review")

    def test_cancellation_retry_limit(self):
        self.runtime.approve(self.pid)
        t = self.runtime.claim()
        self.runtime.cancel(t["id"])
        self.assertFalse(self.runtime.active(t["id"]))
        for _ in range(2):
            self.runtime.retry(t["id"])
            self.runtime.cancel(t["id"])
        with self.assertRaises(ValueError):
            self.runtime.retry(t["id"])

    def test_idempotent_creation(self):
        self.assertEqual(
            self.pid,
            self.store.create("Other", "different brief", "local", "test-key-123"),
        )

    def test_dependency_and_single_writer(self):
        self.runtime.approve(self.pid)
        first = self.runtime.claim()
        self.assertIsNone(self.runtime.claim())
        self.runtime.execute(first)
        qa = self.runtime.claim()
        self.assertEqual(qa["kind"], "qa")

    def test_isolated_projects(self):
        self.runtime.approve(self.pid)
        p2 = self.store.create(
            "Second", "Second task tracker brief", "scripted", "second-key"
        )
        self.runtime.plan(p2)
        self.runtime.approve(p2)
        a = self.runtime.claim()
        b = self.runtime.claim()
        self.assertNotEqual(a["project"], b["project"])
        self.runtime.execute(a)
        self.runtime.execute(b)
        self.assertNotEqual(
            self.store.task(a["id"])["workspace"], self.store.task(b["id"])["workspace"]
        )

    def test_conflict_preserves_partial_work(self):
        self.runtime.approve(self.pid)
        t = self.runtime.claim()
        # Simulate an integration revision changing during generation.
        from unittest.mock import patch

        original = ScriptedProvider.call

        def changed(model, *args):
            with self.store.db() as db:
                db.execute(
                    "UPDATE projects SET revision=revision+1 WHERE id=?", (self.pid,)
                )
            return original(model, *args)

        with patch.object(ScriptedProvider, "call", changed):
            self.runtime.execute(t)
        task = self.store.task(t["id"])
        self.assertEqual(task["state"], "failed")
        self.assertIn("conflict", task["next_action"])
        self.assertTrue(Path(task["workspace"], "index.html").exists())

    def test_repair_invalidates_downstream_gates(self):
        self.runtime.runner = FailingRunner()
        self.runtime.approve(self.pid)
        build = self.run_next()
        qa = self.run_next()
        self.runtime.retry(build["id"])
        self.assertEqual(self.store.task(build["id"])["retries"], 1)
        self.assertEqual(self.store.task(qa["id"])["state"], "ready")
        self.assertEqual(self.runtime.claim()["kind"], "implementation")

    def test_featherlm_coding_dispatch_is_denied(self):
        from unittest.mock import patch
        from forge.providers import LocalProvider

        with patch.dict("os.environ", {"FORGE_MODEL": "featherlm-nano"}):
            with self.assertRaises(ValueError):
                LocalProvider()

    def test_old_attempt_cannot_resume_after_retry(self):
        self.runtime.approve(self.pid)
        old = self.runtime.claim()
        self.runtime.cancel(old["id"])
        self.runtime.retry(old["id"])
        new = self.runtime.claim()
        self.assertNotEqual(old["run_key"], new["run_key"])
        self.assertFalse(self.runtime.active(old["id"], old["run_key"]))
        self.assertTrue(self.runtime.active(new["id"], new["run_key"]))

    def test_reviewer_cannot_complete_cancelled_build(self):
        self.runtime.approve(self.pid)
        build = self.run_next()
        self.run_next()
        review = self.runtime.claim()
        self.runtime.cancel(build["id"])
        self.runtime.execute(review)
        self.assertEqual(self.store.task(build["id"])["state"], "cancelled")
        self.assertEqual(self.store.task(review["id"])["state"], "failed")

    def test_parallel_file_writers_are_isolated(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor

        self.runtime.approve(self.pid)
        other = self.store.create(
            "Parallel", "A distinct parallel task tracker", "scripted", "parallel-key"
        )
        self.runtime.plan(other)
        self.runtime.approve(other)
        a = self.runtime.claim()
        b = self.runtime.claim()
        barrier = threading.Barrier(2)

        def generate(task, project, *args):
            barrier.wait(timeout=5)
            return {
                "files": {"index.html": "<h1>" + project["id"] + "</h1>"},
                "summary": "Concurrent test fixture",
            }

        self.runtime.call_model = generate
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.runtime.execute, t) for t in (a, b)]
            for future in futures:
                future.result(timeout=10)
        for task in (a, b):
            saved = self.store.task(task["id"])
            self.assertEqual(saved["state"], "review")
            self.assertEqual(
                Path(saved["workspace"], "index.html").read_text(),
                "<h1>" + task["project"] + "</h1>",
            )

    def test_traversal_rejected(self):
        from unittest.mock import patch

        self.runtime.approve(self.pid)
        t = self.runtime.claim()
        with patch.object(
            ScriptedProvider,
            "call",
            return_value={"files": {"index.html": "ok", "../escape.js": "bad"}},
        ):
            self.runtime.execute(t)
        self.assertEqual(self.store.task(t["id"])["state"], "failed")
        self.assertFalse(
            (Path(self.store.task(t["id"])["workspace"]).parent / "escape.js").exists()
        )


if __name__ == "__main__":
    unittest.main()
