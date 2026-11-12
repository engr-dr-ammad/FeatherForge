"""Offline operator continuation; stop the platform before using this command."""

import argparse
import fcntl
import json
from forge.store import Store
from forge.runtime import Runtime

parser = argparse.ArgumentParser()
parser.add_argument("--data", required=True)
parser.add_argument("--project", required=True)
args = parser.parse_args()
s = Store(args.data)
worker_lock = open(s.root / "worker.lock", "w")
fcntl.flock(worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
r = Runtime(s)
try:
    project = s.project(args.project)
    qa = next(t for t in project["tasks"] if t["kind"] == "qa")
    review = next(t for t in project["tasks"] if t["kind"] == "review")
    assert qa["state"] == "completed" and qa["evidence"][0]["passed"]
    if review["state"] != "completed":
        r.retry(review["id"])
        task = r.claim()
        assert task and task["id"] == review["id"]
        print("EXPLICIT RESUME: retain implementation and QA; retry review", flush=True)
        r.execute(task)
    project = s.project(args.project)
    print(json.dumps({"project": project["id"], "tasks": project["tasks"]}, indent=2))
    assert all(t["state"] == "completed" for t in project["tasks"])
finally:
    r.pool.shutdown()
    worker_lock.close()
