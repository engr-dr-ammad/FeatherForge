# Security boundary

This release is a trusted single-user local prototype. Do not expose it directly
to the Internet or grant it repositories/credentials you would not trust to its
operator. `FORGE_TOKEN` enables bearer authentication for API reads and mutations;
without it, only loopback clients are accepted. Cross-origin browser mutations
are rejected. TLS, identity-aware access, per-user permissions, audit retention,
rate limits and multi-tenant isolation are not implemented.

Model output can only create bounded HTML/CSS/JS/JSON/Markdown files below its
attempt directory. It cannot choose commands, Docker arguments, credentials,
deployment targets or host paths. Repository/web/tool text is untrusted context.
Provider authentication remains in subprocess environment and is not sent to the
UI or included in event records. Treat user briefs/source files as sensitive:
do not put credentials in them. Automated comprehensive secret scanning is planned.

QA executes code inside a read-only, networkless Docker container, as non-root,
with dropped capabilities, no privilege escalation, RAM/CPU/PID/time bounds and a
small tmpfs. Chromium's internal sandbox is disabled inside this container for
compatibility; Docker is the containment boundary. For hostile multi-tenant code,
use stronger sandboxing such as microVMs and a dedicated authenticated runner.
The trusted Compose orchestrator controls the Docker socket (host-level authority).
Generated applications receive only a read-only artifact mount, never the socket.

Preview uses an opaque-origin sandbox with scripts allowed and CSP blocking
network/form submission. Temporary in-memory localStorage allows safe interaction;
real persistence is exercised in the isolated QA browser. Artifact responses also
carry sandbox CSP. Review artifact content before downloading or running it elsewhere.

Pause prevents future scheduling, not in-flight actions. Cancel terminates model
subprocess groups and removes associated containers. Startup removes interrupted
containers before blocking their tasks. Failed removal is an infrastructure issue;
inspect Docker state before retry. Production credential brokers, spending controls,
and deployment authorization screens are planned; no external mutation tools are
currently available to agents.
