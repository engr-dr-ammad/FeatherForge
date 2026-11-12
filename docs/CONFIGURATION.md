# Server configuration

Configuration is operator-controlled environment, not model-controlled project
content. Restart the server after changing it.

| Variable | Default / purpose |
|---|---|
| FORGE_DATA | repository `data/`; SQLite, event history and artifact attempts |
| FORGE_TOKEN | unset: loopback-only API. Set a strong bearer token for authenticated remote access |
| FORGE_MODEL_URL | `http://127.0.0.1:11434/v1`; local OpenAI-compatible inference |
| FORGE_MODEL | `qwen2.5-coder:7b`; served model name/alias |
| FORGE_MODEL_KEY | `local`; optional provider authentication, never returned by config API |
| FORGE_CONCURRENCY | `2`; concurrent projects, single writer per project. Use `1` on small VFS Docker disks |
| FORGE_TASK_SECONDS | `600`; persisted time budget for new tasks |
| FORGE_EXECUTOR_IMAGE | `featherforge-executor:local`; trusted fixed QA image |
| FORGE_STARTER | unset; optional behavior-free HTML starter path, explicitly labeled in task context |
| FORGE_FEATHERLM_URL | `http://127.0.0.1:8003/v1`; separate experimental completion probe |
| FORGE_FEATHERLM_MODEL | `runs/featherlm-nano/best`; research checkpoint name |
| FORGE_FEATHERLM_KEY | `local`; probe authentication, never included in reports |

Run one platform process per database. Linux process groups and advisory file
locks are required. Do not configure a remote Docker daemon: artifact paths refer
to the local daemon filesystem. Stop the platform before cold backups, then copy
all of FORGE_DATA; retain model/configuration pins separately. Do not put secrets
in briefs, source files, handoffs or training exports. No training export exists
in this release.
