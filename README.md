# FeatherForge

A self-hosted graphical workspace for human-directed AI software delivery.
**Milestone 1 is a local, single-user prototype for small static task-tracker apps.**
It is not a general autonomous software company.

Create a brief, generate and edit a plan, approve execution, then inspect isolated
web artifacts, diffs, independent browser checks, reviewer findings and blockers.
The dashboard labels scripted model runs **SIMULATED MODEL**. No progress percentages
or private chain-of-thought are displayed.

## Quick start (Linux, Python 3.12+, Docker)

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
docker build -f Dockerfile.executor -t featherforge-executor:local .
python -m uvicorn forge.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Create the reference project, select scripted mode,
generate its plan, edit tasks if desired, then **Approve plan & run**. Docker must
be accessible to the server's OS user. Do not run multiple Uvicorn workers.
The database and deliverables live in `data/`; stop the server before backing up this entire directory (SQLite WAL and artifacts must be captured together).

The actual local-model reference app and passing QA/review records are in
[examples/local-model-reference](examples/local-model-reference). It was generated
by Qwen2.5-Coder-7B-Instruct Q2_K with a behavior-free starter and survived an
interrupted review through explicit recovery.

A real coding provider requires a separate local inference server. For Ollama:

```bash
ollama pull qwen2.5-coder:7b
export FORGE_MODEL_URL=http://127.0.0.1:11434/v1
export FORGE_MODEL=qwen2.5-coder:7b
python -m uvicorn forge.app:app --host 127.0.0.1 --port 8000
```

Choose **Real local coding model** when creating the project. llama.cpp and vLLM
use the same OpenAI-compatible `/v1/chat/completions` interface; see
[model compatibility](docs/MODELS.md). The model key, if needed, is supplied only
through `FORGE_MODEL_KEY`, never in the brief or browser. Restart after changing
server configuration.

### Docker Compose

```bash
docker build -f Dockerfile.executor -t featherforge-executor:local .
export FORGE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
# Keep this value in your password manager; the browser asks for it.
export FORGE_UID="$(id -u)" FORGE_GID="$(id -g)"
export FORGE_DOCKER_GID="$(stat -c %g /var/run/docker.sock)"
mkdir -p data
docker compose up -d --build
```

Compose binds localhost and persists `./data`. Its **trusted orchestrator** mounts
the Docker socket to create verification containers, which gives it host-level
Docker authority. It is for a trusted single-user machine, not multi-tenant
hosting. Generated apps never receive that socket. The absolute `PWD` data mount
must match the host daemon's filesystem path. Remote Docker daemons are unsupported.
Use TLS and a proper identity-aware proxy before any remote use. No public cloud
service, paid resource or external app publication is triggered by agents.

In managed environments with TLS inspection, build with the approved CA bundle:
`docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt ...`.
Compose can receive build secrets through an override; never disable TLS checks.

## Validation

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
# Real containers and Chromium; deterministic model output is explicitly simulated:
python -m tests.integration_demo --provider scripted --data data-demo
# Actual local inference + same independent QA; requires configured running model:
python -m tests.integration_demo --provider local --data data-local
```

The orchestration unit tests use a **test double** for QA; integration runs use
real Chromium in Docker. See [validation evidence](docs/VALIDATION.md) for actual
results and limits. Failed QA prevents completion; retries require a human and
are capped at two. Builds with failed downstream checks offer a bounded repair retry using saved code and QA feedback; all downstream gates rerun. Interrupted running tasks become blocked on restart after
associated containers are removed. Completed tasks retain deliverable links.

## Capability status

| Capability | Status |
|---|---|
| Brief, editable three-step plan, role assignment, approval | Implemented |
| Durable task states, event history, ownership, checkpoints | Implemented and unit tested |
| Isolated directories, single writer per project, revision conflict detection | Implemented and unit tested |
| Networkless bounded Docker browser QA | Implemented; see validation report |
| Cancellation of model subprocess and QA container, bounded retries | Implemented; see validation report |
| Board, handoff graph, source/diff/evidence, sandboxed preview | Implemented; see validation report |
| Nine role instruction profiles; enable/disable/edit | Implemented configuration; only PM/frontend/backend/QA/reviewer used in milestone |
| FeatherLM Nano | Experimental evaluation-only; not qualified for coding |
| Arbitrary projects, custom role types, Git integration, deployment agents | Planned |
| Reviewed reusable skill registry, offline learning pipeline | Planned; no collection or weight updates occur |
| Multi-user auth, distributed workers, migration management | Planned |

The preview has opaque origin and blocks network access; it uses temporary storage.
QA verifies real persistent storage in an isolated browser. No automatic Git merges
or app deployment happen. The first milestone deliberately accepts a three-task
implementation → QA → reviewer chain; dependency and handoff visualization reflect
that actual chain.

[Architecture and data model](docs/ARCHITECTURE.md) · [Implementation plan](docs/PLAN.md)
· [Model roadmap](docs/MODEL_ROADMAP.md) · [Security](SECURITY.md)

Platform license: MIT. Model weights and training data keep their own licenses;
none are included in this repository.

For a Linux user-service installation under `~/FeatherForge`, copy
`deploy/featherforge.service` to `~/.config/systemd/user/`, put model configuration
in `~/.config/featherforge/environment` (mode 0600), and run
`systemctl --user daemon-reload && systemctl --user enable --now featherforge`.
The unit is supplied as a template; systemd service installation is not tested in
the development container. Adjust paths if using another checkout location.
