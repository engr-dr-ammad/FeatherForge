# Architecture and data model

Browser → FastAPI → SQLite (WAL) → single durable scheduler → bounded model-call
subprocess or Docker browser executor. Polling refreshes the dashboard every four
seconds; an authenticated SSE activity endpoint is also available. SQLite
transactions atomically claim tasks and serialize project artifact revisions.
An OS file lock prevents multiple platform workers sharing the same database.
Different projects may run concurrently (`FORGE_CONCURRENCY`, default 2); tasks
within one project are serialized. This favors safe integration over throughput.

## Persistence

- `projects`: title, versioned brief, provider, human approval, scheduling pause,
  integration revision, creation time.
- `tasks`: objective/title, role owner, kind, persisted state, dependency IDs,
  acceptance criteria, task context linked to brief version, workspace, artifact
  map, verification evidence, next action, retries, time budget (configurable via FORGE_TASK_SECONDS, default 600 seconds), checkpoint,
  unique execution key, base project revision.
- `events`: ordered observable actions and concise summaries with timestamps and
  project/task provenance; never private reasoning.
- `decisions`: initial scope with brief version. Runtime retrieves original scope,
  acceptance and prior decisions. Full decision editing is a later milestone.
- `requests`: unique creation idempotency keys prevent duplicate projects.
- `roles`: explicit instructions and enable/disable configuration. Tools are
  constrained by task kind: implementation can emit bounded text files only;
  QA can run only the fixed verification executor; review can approve/report.

## State transitions

`backlog → ready → running → review → completed` is the build path. Verification
and review tasks use `running → completed` when their relevant gates pass.
Every running task can fail, be cancelled, or become blocked after interruption.
The build stays in review while QA and reviewer run. Failed QA leaves the build
uncompleted and prevents review scheduling. Human retry from failed/blocked/
cancelled returns to ready, capped at two retries. There are no automatic retries
of uncertain operations. Every attempt gets a new directory/execution key.

Before execution, persist brief version, integration revision, ownership and run
key. Generation writes to `workspaces/<task>/<attempt>/`. It never writes the
repository or another task directory. A revision check before integration blocks
conflicting writers and preserves partial artifacts. Diff is a complete file-add
patch for this initial reference build, not a claimed Git commit or merged branch.
QA reads the build snapshot through a read-only mount. Review sees exact files
and saved QA evidence. Completed build, QA and review tasks link to their files
or evidence. No automatic pruning removes completed artifacts.

## Recovery and permissions

On startup, stop containers for previously running task execution keys, then mark
those tasks blocked with an inspect-and-retry action. Completed records and files
are retained. A fresh model generation can be retried explicitly; no uncertain
external mutation is repeated because models have no external mutation tools.
A bounded build repair consumes a retry, retrieves prior code and QA feedback, and resets downstream checks to ready. Prior attempt directories remain intact. Model subprocesses receive a Linux parent-death kill signal to prevent orphaned requests after hard crashes. Pause stops new scheduling; cancellation stops the model-call subprocess/process
group and removes the named verification container. Shutdown cancels active work.
Plan generation is synchronous with a provider timeout; its transaction refuses
a duplicate saved plan. It is not a cancellable background task yet.

Task scope is frozen after approval. Requirement changes require a new revised
project, avoiding silent reinterpretation of active work. Custom plans with many
tasks, editable DAGs, Git worktrees/merge review, richer decision conflict
resolution, skill retrieval and resumable streaming generation remain planned.
SQLite has no migrations yet: schema changes require explicit versioned migrations
before future releases. This prototype is Linux-only due to process groups/flock.
