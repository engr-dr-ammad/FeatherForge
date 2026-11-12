"""Run genuine Docker QA. Model can be scripted (clearly labeled) or local."""

import argparse
import fcntl
import json
import os
import time
from forge.store import Store
from forge.runtime import Runtime

p = argparse.ArgumentParser()
p.add_argument("--provider", choices=["scripted", "local"], default="scripted")
p.add_argument("--data", default="data-demo")
p.add_argument("--repair", action="store_true")
args = p.parse_args()
s = Store(args.data)
worker_lock = open(s.root / "worker.lock", "w")
fcntl.flock(worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
r = Runtime(s)
pid = s.create(
    "Task tracker · " + args.provider,
    "Build a small accessible task tracker web app. Add tasks, mark complete, delete, persist after reload. Self-contained index.html. Use a labeled textbox, Add task button, checkbox and Delete buttons.",
    args.provider,
    "demo-" + args.provider + "-" + str(time.time_ns()),
)
print("PROJECT", pid, flush=True)
try:
    r.plan(pid)
    r.approve(pid)
    for _ in range(3):
        t = r.claim()
        if not t:
            break
        print("RUN", t["kind"], flush=True)
        r.execute(t)
        print(
            "STATE",
            s.task(t["id"])["state"],
            s.task(t["id"])["next_action"],
            flush=True,
        )
    project = s.project(pid)
    if args.repair:
        for attempt in range(2):
            build = next(x for x in project["tasks"] if x["kind"] == "implementation")
            if all(x["state"] == "completed" for x in project["tasks"]):
                break
            if build["state"] != "review" or not any(
                x["state"] == "failed" for x in project["tasks"]
            ):
                break
            print("OPERATOR AUTHORIZED REPAIR", attempt + 1, flush=True)
            r.retry(build["id"])
            for _ in range(3):
                t = r.claim()
                if not t:
                    break
                print("REPAIR RUN", t["kind"], flush=True)
                r.execute(t)
                print(
                    "REPAIR STATE",
                    s.task(t["id"])["state"],
                    s.task(t["id"])["next_action"],
                    flush=True,
                )
            project = s.project(pid)
    result = {
        "project": pid,
        "provider": args.provider,
        "starter": os.getenv("FORGE_STARTER"),
        "tasks": [
            {
                k: t[k]
                for k in ("id", "kind", "state", "artifacts", "evidence", "next_action")
            }
            for t in project["tasks"]
        ],
    }
    print(json.dumps(result, indent=2), flush=True)
    assert len(project["tasks"]) == 3 and all(
        t["state"] == "completed" for t in project["tasks"]
    ), "Workflow did not pass all gates"
finally:
    r.pool.shutdown()
    worker_lock.close()
