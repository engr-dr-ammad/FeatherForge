import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from forge.runtime import Runtime
from forge.store import Store


class CancellationTest(unittest.TestCase):
    def test_parent_guard_accepts_owner_and_rejects_stale_owner(self):
        import json
        import os
        import subprocess
        import sys

        payload = json.dumps(
            {
                "provider": "scripted",
                "role": "frontend",
                "objective": "reference",
                "context": {},
            }
        )
        result = subprocess.run(
            [sys.executable, "-m", "forge.invoke"],
            input=payload,
            text=True,
            capture_output=True,
            env={**os.environ, "FORGE_PARENT_PID": str(os.getpid())},
            timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("index.html", json.loads(result.stdout)["files"])
        result = subprocess.run(
            [sys.executable, "-m", "forge.invoke"],
            input=payload,
            text=True,
            capture_output=True,
            env={**os.environ, "FORGE_PARENT_PID": "-1"},
            timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_model_subprocess_is_killed(self):
        import subprocess

        with tempfile.TemporaryDirectory() as root:
            s = Store(root)
            r = Runtime(s)
            pid = s.create(
                "Test", "Cancellation reference test", "scripted", "cancel-test"
            )
            r.plan(pid)
            r.approve(pid)
            t = r.claim()
            real_popen = subprocess.Popen
            children = []

            def sleeping(*args, **kwargs):
                child = real_popen(["/bin/sleep", "30"], **kwargs)
                children.append(child)
                return child

            errors = []

            def call():
                try:
                    r.call_model(t, s.project(pid), "frontend", "test", {})
                except ValueError as exc:
                    errors.append(str(exc))

            with patch("forge.runtime.subprocess.Popen", side_effect=sleeping):
                thread = threading.Thread(target=call)
                thread.start()
                deadline = time.monotonic() + 5
                while not children and time.monotonic() < deadline:
                    time.sleep(0.01)
                s.update(t["id"], state="cancelled")
                thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertIsNotNone(children[0].poll())
            self.assertTrue(errors)
            r.pool.shutdown()


if __name__ == "__main__":
    unittest.main()
