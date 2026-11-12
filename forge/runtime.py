import concurrent.futures
import json
import difflib
import os
import subprocess
import threading
import time
import uuid
import signal
import sys
from pathlib import Path
from .providers import provider, ROLES

PLAN_SCHEMA = {
    "tasks": [
        {
            "key": "build",
            "title": "Build task tracker",
            "role": "frontend",
            "kind": "implementation",
            "dependencies": [],
            "acceptance": ["add, complete, delete, persist tasks"],
        },
        {
            "key": "qa",
            "title": "Verify behavior",
            "role": "qa",
            "kind": "qa",
            "dependencies": ["build"],
            "acceptance": ["passing browser checks"],
        },
        {
            "key": "review",
            "title": "Review code",
            "role": "reviewer",
            "kind": "review",
            "dependencies": ["qa"],
            "acceptance": ["review approved"],
        },
    ]
}


class Runtime:
    def __init__(self, store, runner=None):
        self.store = store
        self.runner = runner or DockerRunner()
        self.stop = threading.Event()
        self.pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=int(os.getenv("FORGE_CONCURRENCY", "2"))
        )
        self.futures = set()

    def plan(self, pid):
        p = self.store.project(pid)
        if p["approved"] or p["tasks"]:
            raise ValueError("Plan already exists; edit tasks before approval")
        with self.store.db() as db:
            manager = db.execute(
                "SELECT * FROM roles WHERE name='project_manager'"
            ).fetchone()
        if manager and not manager["enabled"]:
            raise ValueError("Project manager role is disabled")
        result = provider(p["provider"]).call(
            "project_manager",
            p["brief"],
            {
                "role_instructions": manager["instructions"]
                if manager
                else ROLES["project_manager"],
                "schema": PLAN_SCHEMA,
                "scope": "A small static task tracker web app. Exactly implementation -> qa -> review. No external services.",
            },
        )
        tasks = result.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError(
                "Model plan must contain a tasks array; revise provider or retry plan generation"
            )
        if len(tasks) != 3 or [t["kind"] for t in tasks] != [
            "implementation",
            "qa",
            "review",
        ]:
            raise ValueError("Milestone supports exactly implementation, QA and review")
        ids = {t["key"]: uuid.uuid4().hex for t in tasks}
        if len(ids) != 3:
            raise ValueError("Duplicate task keys")
        for i, t in enumerate(tasks):
            if t["role"] not in ROLES:
                raise ValueError("Unknown role")
            if not isinstance(t["acceptance"], list) or not t["acceptance"]:
                raise ValueError("Acceptance criteria required")
            expected = [] if i == 0 else [tasks[i - 1]["key"]]
            if t["dependencies"] != expected:
                raise ValueError("Invalid milestone dependency chain")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM tasks WHERE project=?", (pid,)).fetchone():
                raise ValueError("Concurrent plan already saved")
            for t in tasks:
                db.execute(
                    "INSERT INTO tasks(id,project,title,role,kind,state,deps,acceptance,context,budget) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        ids[t["key"]],
                        pid,
                        t["title"],
                        t["role"],
                        t["kind"],
                        "backlog",
                        json.dumps([ids[d] for d in t["dependencies"]]),
                        json.dumps(t["acceptance"]),
                        json.dumps(
                            {"brief_version": p["version"], "brief": p["brief"]}
                        ),
                        int(os.getenv("FORGE_TASK_SECONDS", "600")),
                    ),
                )
            self.store.event(
                db,
                pid,
                None,
                "plan",
                "Plan generated; awaiting human review and approval",
            )
        return self.store.project(pid)

    def approve(self, pid):
        with self.store.db() as db:
            if (
                db.execute(
                    "SELECT count(*) FROM tasks WHERE project=?", (pid,)
                ).fetchone()[0]
                != 3
            ):
                raise ValueError("Generate the plan first")
            db.execute("UPDATE projects SET approved=1 WHERE id=?", (pid,))
            db.execute(
                "UPDATE tasks SET state='ready' WHERE project=? AND state='backlog'",
                (pid,),
            )
            self.store.event(
                db, pid, None, "approval", "Human approved plan and isolated execution"
            )

    def log(self, t, kind, message):
        with self.store.db() as db:
            self.store.event(db, t["project"], t["id"], kind, message)

    def call_model(self, t, p, role, objective, context):
        payload = json.dumps(
            {
                "provider": p["provider"],
                "role": role,
                "objective": objective,
                "context": context,
            }
        )
        proc = subprocess.Popen(
            [sys.executable, "-m", "forge.invoke"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env={**os.environ, "FORGE_PARENT_PID": str(os.getpid())},
        )
        start = time.monotonic()
        first = True
        try:
            while True:
                if (
                    not self.active(t["id"], t["run_key"])
                    or time.monotonic() - start > t["budget"]
                ):
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    raise ValueError(
                        "Model call cancelled or task time budget exceeded"
                    )
                try:
                    output, error = proc.communicate(
                        input=payload if first else None, timeout=0.2
                    )
                    break
                except subprocess.TimeoutExpired:
                    first = False
            if proc.returncode:
                raise ValueError(
                    "Model request failed: "
                    + error[:100]
                    + "; inspect configured endpoint"
                )
            if len(output) > 1_000_000:
                raise ValueError("Model response exceeded artifact budget")
            result = json.loads(output)
            self.log(
                t,
                "usage",
                json.dumps(
                    {
                        "model": result.get("_model", p["provider"]),
                        "tokens": result.get("_usage", {}),
                        "duration_seconds": round(time.monotonic() - start, 2),
                    }
                ),
            )
            return result
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()

    def active(self, tid, run_key=None):
        task = self.store.task(tid)
        return task["state"] == "running" and (
            run_key is None or task["run_key"] == run_key
        )

    def execute(self, t):
        try:
            p = self.store.project(t["project"])
            model = provider(p["provider"])
            with self.store.db() as db:
                role = db.execute(
                    "SELECT * FROM roles WHERE name=?", (t["role"],)
                ).fetchone()
            if role and not role["enabled"]:
                raise ValueError("Assigned role is disabled")
            context = {
                "brief": p["brief"],
                "acceptance": t["acceptance"],
                "decisions": p["decisions"],
                "role_instructions": role["instructions"] if role else ROLES[t["role"]],
            }
            self.store.update(
                t["id"],
                checkpoint={
                    "brief_version": p["version"],
                    "revision": p["revision"],
                    "run_key": t["run_key"],
                },
                base_revision=p["revision"],
            )
            if t["kind"] == "implementation":
                workspace = self.store.root / "workspaces" / t["id"] / t["run_key"]
                workspace.mkdir(parents=True)
                workspace.chmod(0o755)
                self.store.update(
                    t["id"],
                    workspace=str(workspace),
                    next_action="Generate bounded web files",
                )
                context["output_schema"] = {
                    "files": {
                        "index.html": "complete self-contained accessible task tracker HTML/JS/CSS"
                    },
                    "summary": "concise observable changes",
                }
                if t["workspace"]:
                    previous = Path(t["workspace"]) / "index.html"
                    context["previous_implementation"] = (
                        previous.read_text() if previous.exists() else ""
                    )
                    context["qa_feedback"] = [
                        {"state": x["state"], "evidence": x["evidence"]}
                        for x in p["tasks"]
                        if x["kind"] == "qa"
                    ]
                    context["review_feedback"] = [
                        {"state": x["state"], "evidence": x["evidence"]}
                        for x in p["tasks"]
                        if x["kind"] == "review"
                    ]
                starter = os.getenv("FORGE_STARTER")
                if starter:
                    context["starter_html"] = Path(starter).read_text()[:12000]
                    context["starter_instruction"] = (
                        "Complete the missing JavaScript in this explicit starter. Preserve its form and tasks list. No CSS or extra features are needed. Return the complete HTML file."
                    )
                context["constraints"] = (
                    "No dependencies, network calls, remote assets, or backend. Add task via labeled input and Add task button, checkbox complete, Delete button, localStorage persistence. Use textContent for user input. The textbox MUST have an actual label element with matching for/id, or aria-label; placeholder alone is NOT accessible. Render task titles in their own span. Use stable unique task ids. Keep one global tasks array; render() should take no arguments so deletion cannot shadow the global state. Persist after each change."
                )
                self.store.update(t["id"], context=context)
                self.log(
                    t,
                    "model",
                    "Request bounded implementation JSON from "
                    + model.name
                    + (" with behavior-free HTML starter" if starter else ""),
                )
                result = self.call_model(t, p, t["role"], t["title"], context)
                if not self.active(t["id"], t["run_key"]):
                    return
                files = result["files"]
                if (
                    not isinstance(files, dict)
                    or "index.html" not in files
                    or len(files) > 20
                ):
                    raise ValueError("Expected <=20 files including index.html")
                total = 0
                for name, content in files.items():
                    target = (workspace / name).resolve()
                    if (
                        not target.is_relative_to(workspace)
                        or target == workspace
                        or not isinstance(content, str)
                    ):
                        raise ValueError("Unsafe artifact path")
                    if target.suffix not in (".html", ".css", ".js", ".json", ".md"):
                        raise ValueError("Unsupported artifact type")
                    total += len(content.encode())
                    if total > 500_000:
                        raise ValueError("Artifact budget exceeded")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
                    target.chmod(0o644)
                # Human-readable complete diff against empty task workspace.
                diff = "".join(
                    "".join(
                        difflib.unified_diff(
                            [],
                            [line + "\n" for line in body.splitlines()],
                            fromfile="/dev/null",
                            tofile="b/" + name,
                        )
                    )
                    for name, body in files.items()
                )
                (workspace / "changes.diff").write_text(diff)
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = db.execute(
                        "SELECT revision FROM projects WHERE id=?", (p["id"],)
                    ).fetchone()[0]
                    state = db.execute(
                        "SELECT state FROM tasks WHERE id=?", (t["id"],)
                    ).fetchone()[0]
                    if state != "running":
                        return
                    if (
                        db.execute(
                            "SELECT run_key FROM tasks WHERE id=?", (t["id"],)
                        ).fetchone()[0]
                        != t["run_key"]
                    ):
                        return
                    if current != p["revision"]:
                        raise ValueError(
                            "Integration conflict: project revision changed; partial work preserved"
                        )
                    db.execute(
                        "UPDATE projects SET revision=revision+1 WHERE id=?", (p["id"],)
                    )
                    db.execute(
                        "UPDATE tasks SET state='review',artifacts=?,next_action='Await QA and code review' WHERE id=?",
                        (
                            json.dumps(
                                {
                                    "files": list(files),
                                    "diff": "changes.diff",
                                    "preview": "index.html",
                                    "provider": model.name,
                                }
                            ),
                            t["id"],
                        ),
                    )
                self.log(t, "artifact", result.get("summary", "Files generated"))
                # Dependency scheduler allows QA to inspect implementation in review.
            elif t["kind"] == "qa":
                build = next(x for x in p["tasks"] if x["kind"] == "implementation")
                if build["state"] != "review":
                    raise ValueError("Implementation is not ready for verification")
                self.store.update(
                    t["id"],
                    workspace=build["workspace"],
                    next_action="Run independent browser acceptance suite",
                )
                self.log(
                    t,
                    "tool",
                    "Run fixed reference acceptance suite in resource-limited, networkless Docker container",
                )
                result = self.runner.run(
                    t,
                    Path(build["workspace"]),
                    lambda: self.active(t["id"], t["run_key"]),
                )
                if not self.active(t["id"], t["run_key"]):
                    return
                self.store.update(
                    t["id"],
                    evidence=[result],
                    artifacts={"verification": "qa-result.json"},
                )
                (Path(build["workspace"]) / "qa-result.json").write_text(
                    json.dumps(result, indent=2)
                )
                if not result["passed"]:
                    raise ValueError(
                        "Acceptance checks failed; inspect verification evidence"
                    )
                if self.store.task(build["id"])["state"] != "review":
                    raise ValueError("Build was cancelled during verification")
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if (
                        db.execute(
                            "SELECT state FROM tasks WHERE id=?", (build["id"],)
                        ).fetchone()[0]
                        != "review"
                    ):
                        raise ValueError("Build was cancelled during verification")
                    db.execute(
                        "UPDATE tasks SET state='completed',next_action='Reviewer must inspect passing evidence' WHERE id=? AND state='running' AND run_key=?",
                        (t["id"], t["run_key"]),
                    )
            elif t["kind"] == "review":
                build = next(x for x in p["tasks"] if x["kind"] == "implementation")
                qa = next(x for x in p["tasks"] if x["kind"] == "qa")
                if (
                    qa["state"] != "completed"
                    or not qa["evidence"]
                    or not qa["evidence"][0]["passed"]
                ):
                    raise ValueError("Passing verification required")
                context.update(
                    {
                        "files": {
                            f: (Path(build["workspace"]) / f).read_text()
                            for f in build["artifacts"]["files"]
                        },
                        "verification": qa["evidence"],
                        "output_schema": {
                            "approved": True,
                            "summary": "Concrete findings, evidence and limitations",
                        },
                    }
                )
                self.log(
                    t,
                    "model",
                    "Review exact artifact snapshot and recorded QA evidence with "
                    + model.name,
                )
                result = self.call_model(t, p, "reviewer", t["title"], context)
                if not self.active(t["id"], t["run_key"]):
                    return
                self.store.update(
                    t["id"],
                    workspace=build["workspace"],
                    evidence=[result],
                    artifacts={"review": "review.json"},
                )
                (Path(build["workspace"]) / "review.json").write_text(
                    json.dumps(result, indent=2)
                )
                if result.get("approved") is not True:
                    raise ValueError("Reviewer found unresolved issues")
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current_review = db.execute(
                        "SELECT state FROM tasks WHERE id=? AND run_key=?",
                        (t["id"], t["run_key"]),
                    ).fetchone()
                    if not current_review or current_review[0] != "running":
                        return
                    if (
                        db.execute(
                            "SELECT state FROM tasks WHERE id=?", (build["id"],)
                        ).fetchone()[0]
                        != "review"
                    ):
                        raise ValueError("Build no longer available for completion")
                    if (
                        db.execute(
                            "SELECT state FROM tasks WHERE id=?", (qa["id"],)
                        ).fetchone()[0]
                        != "completed"
                    ):
                        raise ValueError("QA no longer complete")
                    db.execute(
                        "UPDATE tasks SET state='completed',next_action='Deliverable available for human inspection' WHERE id IN (?,?)",
                        (build["id"], t["id"]),
                    )
                    build_artifacts = {
                        **build["artifacts"],
                        "verification": "qa-result.json",
                        "review": "review.json",
                    }
                    db.execute(
                        "UPDATE tasks SET artifacts=?,evidence=? WHERE id=?",
                        (
                            json.dumps(build_artifacts),
                            json.dumps(
                                [
                                    {
                                        "verification_task": qa["id"],
                                        "review_task": t["id"],
                                        "passed": True,
                                    }
                                ]
                            ),
                            build["id"],
                        ),
                    )
                self.log(t, "review", result["summary"])
            self.log(t, "checkpoint", "Execution checkpoint saved")
        except Exception as exc:
            if self.active(t["id"], t["run_key"]):
                # Error detail from arbitrary upstream endpoints may contain secrets: only fixed class + safe local errors.
                message = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else type(exc).__name__ + "; inspect local service health"
                )
                self.store.update(t["id"], state="failed", next_action=message)
                self.log(t, "failure", message)

    def claim(self):
        # QA can consume a review-state build; all other dependencies require completion.
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT t.* FROM tasks t JOIN projects p ON p.id=t.project WHERE t.state='ready' AND p.approved=1 AND p.paused=0 ORDER BY t.rowid"
            ).fetchall()
            for row in rows:
                t = self.store.decode(dict(row))
                if db.execute(
                    "SELECT 1 FROM tasks WHERE project=? AND state='running'",
                    (t["project"],),
                ).fetchone():
                    continue
                allowed = (
                    ("completed", "review") if t["kind"] == "qa" else ("completed",)
                )
                states = [
                    db.execute("SELECT state FROM tasks WHERE id=?", (d,)).fetchone()
                    for d in t["deps"]
                ]
                if not all(x and x[0] in allowed for x in states):
                    continue
                db.execute(
                    "UPDATE tasks SET state='running',run_key=? WHERE id=?",
                    (uuid.uuid4().hex, t["id"]),
                )
                self.store.event(
                    db, t["project"], t["id"], "started", "Task claimed; " + t["role"]
                )
                tid = t["id"]
                break
            else:
                return None
        return self.store.task(tid)

    def loop(self):
        while not self.stop.is_set():
            self.futures = {f for f in self.futures if not f.done()}
            while len(self.futures) < self.pool._max_workers:
                t = self.claim()
                if not t:
                    break
                self.futures.add(self.pool.submit(self.execute, t))
            self.stop.wait(0.3)

    def cancel(self, tid):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            if not row:
                raise ValueError("Task not found")
            t = self.store.decode(dict(row))
            if t["state"] in ("completed", "cancelled"):
                raise ValueError("Terminal task cannot be cancelled")
            db.execute(
                "UPDATE tasks SET state='cancelled',next_action='Cancelled by human; partial artifacts preserved' WHERE id=?",
                (tid,),
            )
        self.runner.cancel(t)
        self.log(
            t,
            "cancelled",
            "Cancellation requested; associated verification container removed",
        )

    def retry(self, tid):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            if not row:
                raise ValueError("Task not found")
            t = dict(row)
            repair = (
                t["kind"] == "implementation"
                and t["state"] == "review"
                and db.execute(
                    "SELECT 1 FROM tasks WHERE project=? AND state='failed'",
                    (t["project"],),
                ).fetchone()
            )
            if t["state"] not in ("failed", "blocked", "cancelled") and not repair:
                raise ValueError(
                    "Only stopped tasks or builds with failed downstream checks may retry"
                )
            if t["retries"] >= 2:
                raise ValueError(
                    "Retry limit reached; revise scope or create a new project"
                )
            db.execute(
                "UPDATE tasks SET state='ready',retries=retries+1,next_action='Explicit retry authorized' WHERE id=?",
                (tid,),
            )
            if repair:
                db.execute(
                    "UPDATE tasks SET state='ready',next_action='Await repaired build and rerun verification' WHERE project=? AND kind IN ('qa','review')",
                    (t["project"],),
                )
                self.store.event(
                    db,
                    t["project"],
                    tid,
                    "repair",
                    "Human authorized bounded repair from saved QA evidence; downstream gates reset",
                )


class DockerRunner:
    image = os.environ.get("FORGE_EXECUTOR_IMAGE", "featherforge-executor:local")

    def name(self, t):
        return "ff-" + t["id"] + "-" + (t["run_key"] or "none")[:8]

    def cancel(self, t):
        subprocess.run(
            ["docker", "rm", "-f", self.name(t)], capture_output=True, timeout=15
        )

    def run(self, t, workspace, active):
        name = self.name(t)
        cmd = [
            "docker",
            "run",
            "--name",
            name,
            "--network=none",
            "--memory=768m",
            "--cpus=1",
            "--pids-limit=128",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=1000:1000",
            "--tmpfs",
            "/tmp:rw,nosuid,size=128m",
            "--mount",
            f"type=bind,src={workspace},dst=/project,readonly",
            self.image,
        ]
        start = time.monotonic()
        with __import__("tempfile").TemporaryFile() as output:
            proc = subprocess.Popen(
                cmd, stdout=output, stderr=subprocess.STDOUT, start_new_session=True
            )
            try:
                while proc.poll() is None:
                    if not active() or time.monotonic() - start > t["budget"]:
                        self.cancel(t)
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        break
                    time.sleep(0.2)
                output.seek(0)
                log = output.read(64000).decode(errors="replace")
                return {
                    "passed": proc.returncode == 0,
                    "exit_code": proc.returncode,
                    "tool": "docker isolated browser acceptance",
                    "command": cmd[:2] + ["[resource-limited executor]"],
                    "duration_seconds": round(time.monotonic() - start, 2),
                    "output": log,
                    "simulated": False,
                }
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                self.cancel(t)
