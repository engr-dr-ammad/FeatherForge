import contextlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

STATES = (
    "backlog",
    "ready",
    "running",
    "review",
    "completed",
    "blocked",
    "failed",
    "cancelled",
)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "forge.sqlite3"
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, title TEXT, brief TEXT, version INTEGER DEFAULT 1, provider TEXT, approved INTEGER DEFAULT 0, paused INTEGER DEFAULT 0, revision INTEGER DEFAULT 0, created REAL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, project TEXT, title TEXT, role TEXT, kind TEXT, state TEXT, deps TEXT, acceptance TEXT, context TEXT DEFAULT '{}', workspace TEXT, artifacts TEXT DEFAULT '{}', evidence TEXT DEFAULT '[]', next_action TEXT DEFAULT '', retries INTEGER DEFAULT 0, budget INTEGER DEFAULT 180, checkpoint TEXT DEFAULT '{}', run_key TEXT, base_revision INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT, task TEXT, kind TEXT, message TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS requests(key TEXT PRIMARY KEY, project TEXT);
            CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT, version INTEGER, body TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS roles(name TEXT PRIMARY KEY, enabled INTEGER DEFAULT 1, instructions TEXT);
            """)

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, project, task, kind, message):
        db.execute(
            "INSERT INTO events(project,task,kind,message,created) VALUES(?,?,?,?,?)",
            (project, task, kind, message, time.time()),
        )

    def create(self, title, brief, provider, key):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT project FROM requests WHERE key=?", (key,)
            ).fetchone()
            if old:
                return old[0]
            pid = uuid.uuid4().hex
            db.execute(
                "INSERT INTO projects(id,title,brief,provider,created) VALUES(?,?,?,?,?)",
                (pid, title, brief, provider, time.time()),
            )
            db.execute("INSERT INTO requests VALUES(?,?)", (key, pid))
            db.execute(
                "INSERT INTO decisions(project,version,body,created) VALUES(?,?,?,?)",
                (pid, 1, "Initial brief: " + brief, time.time()),
            )
            self.event(
                db,
                pid,
                None,
                "project",
                "Project created; generate a plan for human approval",
            )
            return pid

    def project(self, pid):
        with self.db() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
            if not row:
                raise ValueError("Project not found")
            p = dict(row)
            p["tasks"] = [
                self.decode(dict(r))
                for r in db.execute(
                    "SELECT * FROM tasks WHERE project=? ORDER BY rowid", (pid,)
                )
            ]
            p["events"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM events WHERE project=? ORDER BY id DESC LIMIT 200",
                    (pid,),
                )
            ]
            p["decisions"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM decisions WHERE project=? ORDER BY id", (pid,)
                )
            ]
            return p

    def decode(self, t):
        for k in (
            "deps",
            "acceptance",
            "context",
            "artifacts",
            "evidence",
            "checkpoint",
        ):
            t[k] = json.loads(t[k])
        return t

    def task(self, tid):
        with self.db() as db:
            t = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            if not t:
                raise ValueError("Task not found")
            return self.decode(dict(t))

    def update(self, tid, **values):
        for k in (
            "deps",
            "acceptance",
            "context",
            "artifacts",
            "evidence",
            "checkpoint",
        ):
            if k in values:
                values[k] = json.dumps(values[k])
        with self.db() as db:
            db.execute(
                "UPDATE tasks SET "
                + ",".join(k + "=?" for k in values)
                + " WHERE id=?",
                (*values.values(), tid),
            )

    def recover(self):
        with self.db() as db:
            rows = db.execute("SELECT * FROM tasks WHERE state='running'").fetchall()
            for t in rows:
                db.execute(
                    "UPDATE tasks SET state='blocked',next_action='Interrupted execution: inspect checkpoint and artifacts, then retry explicitly' WHERE id=?",
                    (t["id"],),
                )
                self.event(
                    db,
                    t["project"],
                    t["id"],
                    "recovery",
                    "Execution interrupted; no uncertain operation automatically retried",
                )
