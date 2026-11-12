"""A real failed browser check must prevent completion and review scheduling."""

import json
import tempfile
from forge.store import Store
from forge.runtime import Runtime

with tempfile.TemporaryDirectory(prefix="forge-fail-") as root:
    s = Store(root)
    r = Runtime(s)
    pid = s.create(
        "Broken app",
        "Intentional failure of reference task tracker",
        "scripted",
        "failed-check-test",
    )
    r.plan(pid)
    r.approve(pid)
    r.call_model = lambda *args: {
        "files": {
            "index.html": '<!doctype html><html lang="en"><title>Broken</title><label for="task">Task</label><input id="task"><button>Add task</button></html>'
        },
        "summary": "Intentionally missing add behavior",
    }
    t = r.claim()
    r.execute(t)
    qa = r.claim()
    r.execute(qa)
    task = s.task(qa["id"])
    assert task["state"] == "failed"
    assert task["evidence"][0]["passed"] is False
    assert r.claim() is None
    assert s.task(t["id"])["state"] == "review"
    print(
        "PASS: actual failed browser check prevents build completion and reviewer scheduling"
    )
    print(json.dumps(task["evidence"], indent=2))
    r.pool.shutdown()
