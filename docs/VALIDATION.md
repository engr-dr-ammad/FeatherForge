# Validation record

This report distinguishes implementation from observed results. Recorded on
2026-11-12 in a Linux environment with 3 CPU cores, an 8 GiB memory limit (host reports ~10 GB), no GPU and a small
Docker VFS filesystem. See the adjacent `evidence/` logs for actual runs.

- **17 automated unit/API checks passed:** human approval gate, creation
  idempotency, dependency ordering, one writer per project, separate project
  directories, revision conflict/partial artifact preservation, failed QA gate,
  restart record recovery, cancellation/retry cap, path traversal, scope freeze,
  actual model child-process termination, bounded repair, FeatherLM dispatch gate, stale-attempt exclusion, cancelled-build completion protection and actual concurrent file writers in separate project directories.
  Some checks share test methods. Unit QA uses an explicitly simulated test double.
- **Dashboard Chromium test passed:** create, plan, edit task, approve, wait for all
  three completion gates, interact with the opaque-origin preview, no JS errors.
  Screenshot: `evidence/dashboard.png`. Simulated model, real browser/QA.
- **Scripted reference workflow passed against real Docker Chromium:** add,
  persistent storage, complete, delete, injection handling, accessible input and
  absence of page errors. The final expanded suite including deletion persistence passed; see
  `scripted-run.txt`.
- **Real process restart and container cancellation passed:** an interrupted task
  retained its owner, became blocked and its real associated Docker container was
  removed on startup; explicit cancellation also removed an actual container.
  The final rerun passed and is recorded in `recovery-run.txt`.
- **Live platform completed-work restart passed:** six completed task records
  retained owner, state, workspace and byte-identical artifact hashes after the
  actual dashboard server restarted; `platform-restart-run.txt`.
- **Real failed-check gate passed:** an intentionally broken app failed Chromium
  checks, stayed in review, and never scheduled the reviewer; `failure-run.txt`.
- **Real local model:** Qwen2.5-Coder-1.5B-Instruct Q4_K_M, served by llama.cpp
  build b12322 (4fffab623) on CPU. Initial unconstrained plans failed validation.
  JSON-schema constrained planning passed. The first implementation failed QA;
  see `local-failed-run.txt`. Both 1.5B trials exhausted their bounded repairs. The final 7B run is recorded
  below; no model success is inferred from simulated runs.

Observed infrastructure failures: large Playwright/Ollama Docker images exhausted
storage under VFS. Replaced them with native CPU llama.cpp and a headless-only
browser executor. Non-root script traversal permissions were corrected. Infrastructure
failures were retained as failures and did not cause automatic completion.

Limits: multi-project file separation and integration conflicts are tested at the
runtime level, not across distributed workers. No vLLM/Ollama server-specific run,
FeatherLM weight benchmark, production penetration test, public hosting, arbitrary
repository build, automatic Git merge or training run is claimed. Docker builds
use pinned Python dependency versions but base image tags and OS packages are not
fully reproducible by digest/lock snapshot yet.

## Actual managed-environment restart during the 7B demonstration

The 7B implementation and all independent browser checks passed. A managed runtime
restart interrupted its model review, terminating the temporary native inference
process. The database retained the exact implementation, passing QA evidence and
review owner; recovery marked that unfinished review blocked. Continuation retries
only review, with the same hash-verified model, not the completed build or QA.
The reference artifact is preserved in `examples/local-model-reference/`.
The explicit retry completed successfully: implementation, QA and review all
reached completed. The real reviewer approved the unchanged app. See
`evidence/local-7b-recovery-result.json` and `examples/local-model-reference/review.json`.
This is a scaffold-assisted, aggressively quantized reference demonstration, not
a general coding benchmark or a production accessibility/security certification.


## Deployment artifacts

The non-root `featherforge-platform:local` image built successfully from the
Dockerfile. Compose configuration validates with the required token and Docker
socket group variables. Actual container runtime verification passed: bearer-authenticated API, non-root
worker subprocesses and the complete scripted workflow with real nested Docker
browser QA all succeeded; `evidence/container-deployment-run.json`. Reproduce after
building both images with `python -m tests.container_deployment`. Public hosting and GitHub
publication are separate from this local deployment and require the user's exact
destination authorization; the initial GitHub push was rejected by automatic
approval review. No public deployment is claimed.
