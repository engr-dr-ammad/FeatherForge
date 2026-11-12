"""Real Docker cancellation and process-restart recovery smoke test."""

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from forge.store import Store
from forge.runtime import Runtime

with tempfile.TemporaryDirectory(prefix="forge-recovery-") as root:
    s = Store(root)
    r = Runtime(s)
    pid = s.create(
        "Recovery",
        "Reference restart and container cancellation",
        "scripted",
        "recovery-test",
    )
    r.plan(pid)
    r.approve(pid)
    t = r.claim()
    name = r.runner.name(t)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network=none",
            "--memory=64m",
            "--cpus=.5",
            "--pids-limit=32",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=1000:1000",
            "--entrypoint",
            "python",
            "python:3.12-slim",
            "-c",
            "import time;time.sleep(60)",
        ],
        check=True,
        capture_output=True,
    )
    env = {**os.environ, "FORGE_DATA": root}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "forge.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8002",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                urllib.request.urlopen("http://127.0.0.1:8002/health", timeout=1)
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise RuntimeError("Server failed to restart")
                time.sleep(0.2)
        recovered = Store(root).task(t["id"])
        assert recovered["state"] == "blocked", recovered
        assert recovered["role"] == t["role"]
        result = subprocess.run(["docker", "inspect", name], capture_output=True)
        assert result.returncode != 0, "Interrupted container survived recovery"
        print(
            "PASS real process restart: task owner retained, interrupted task blocked, associated container removed"
        )
    finally:
        process.terminate()
        process.wait(timeout=15)
        r.runner.cancel(t)
        r.pool.shutdown()
    # Verify explicit cancellation against a second actual process/container.
    r.retry(t["id"])
    t = r.claim()
    name = r.runner.name(t)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network=none",
            "--memory=64m",
            "--cpus=.5",
            "--pids-limit=32",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=1000:1000",
            "--entrypoint",
            "python",
            "python:3.12-slim",
            "-c",
            "import time;time.sleep(60)",
        ],
        check=True,
        capture_output=True,
    )
    r.cancel(t["id"])
    assert (
        subprocess.run(["docker", "inspect", name], capture_output=True).returncode != 0
    )
    assert s.task(t["id"])["state"] == "cancelled"
    print("PASS explicit cancellation removes actual child container")
