# Milestone 1 implementation contract

Target inspected: engr-dr-ammad/FeatherForge, empty main on 2026-11-12.
Related source inspected: engr-dr-ammad/FeatherLM, commit 952bd458d52bf151ac99d0a11ff378c94345b108 (README, API routes, license). The temporary inspection clone was removed after audit to reclaim disk; no source was copied.
Reusable by interface: OpenAI chat/completion API; checkpoint metadata; future LoRA,
dataset and evaluation tooling. No model code or weights copied. Nano 13.2M is
explicitly documented upstream as non-instruction-following. No coding benchmark
has been run on it here; implementation assignment is disabled.

1. Persist briefs, editable plans, dependencies, roles, events and evidence in SQLite.
   Accept: restart preserves tasks; interrupted execution becomes blocked for review.
2. Implement one shared runtime and provider protocol. Reviewable JSON plans;
   implementation returns files; QA runs independent, fixed acceptance checks;
   model reviewer inspects code and evidence. Accept: failed checks never complete.
3. Isolate each implementation task and serialize integration by project revision.
   Accept: conflicts block rather than overwrite; Docker has no network, bounded RAM,
   CPU, PIDs, timeout, non-root user and no privileged host mounts.
4. Provide graphical brief/board/handoff/activity/evidence/preview/controls.
   Accept: human approval gates work; task editing, assignment and cancellation work.
5. Package local setup, scripted reference test, real provider configuration,
   security boundaries, license and model development roadmap.
   Accept: report actual tests and distinguish unexecuted integration checks.

Material tradeoffs: SQLite and a single worker avoid a broker for a local MVP.
Independent task directories are equivalent isolated workspaces, with immutable
artifact snapshots rather than automatic Git merging. Static HTML/JS avoids a
frontend build chain for this milestone; React/React Flow remain a later migration.
No arbitrary shell tool or autonomous deployment is exposed to model output.
