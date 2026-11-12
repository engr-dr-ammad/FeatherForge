# Model compatibility and hardware

The platform itself runs on ordinary CPU hardware, ~256 MB plus artifacts. The
browser executor is limited to 768 MB RAM, 1 CPU, 128 PIDs and a configurable task time budget (600 seconds by default). Plan
for at least 10 GB free disk for Docker builds (more with Docker's vfs driver).
A coding model needs its own RAM/VRAM budget; the platform does not include weights.

| Server | Configuration | Status |
|---|---|---|
| Ollama | `FORGE_MODEL_URL=http://127.0.0.1:11434/v1`, `FORGE_MODEL=qwen2.5-coder:7b` | Interface supported; server-specific end-to-end verification not yet claimed |
| llama.cpp llama-server | URL `http://127.0.0.1:8081/v1`, model alias from `--alias` | See validation report for actual CPU run |
| vLLM | URL `http://127.0.0.1:8001/v1`, model served by vLLM | Interface supported, untested here |
| Scripted | project provider `scripted` | Repeatable orchestration fixture, SIMULATED MODEL |
| FeatherLM Nano | upstream `/v1/completions`; chat models require featherlm-v1 template | Experimental evaluation only, coding dispatch denied |

Recommended first deployment: **Qwen2.5-Coder-7B-Instruct**, Apache-2.0 model
license. Q4 weights approximately 4.7 GB; allow ~8–12 GB system RAM for CPU
inference, depending on context. 8 GB+ VRAM generally gives more useful latency.
The 1.5B Instruct Q4 model (~1.1 GB weights; allow 3–5 GB RAM) is a resource-limited
smoke-test option with lower coding reliability. A small reference success does
not establish broad project capability. Pin and record exact weight hashes.

Qwen model licenses are separate from FeatherForge MIT. Retain upstream LICENSE
and NOTICE with redistribution; Apache-2.0 includes attribution/notice and patent
terms and does not grant trademarks. Check the exact model card and any dataset
restrictions before fine-tuning or redistribution. Other Qwen sizes/families may
have different terms. No model or training dataset is relicensed by this platform.

The provider uses OpenAI JSON-schema constrained responses (the server must implement this extension) and expects JSON: plans with three linked task records, implementations
with a filename-to-text map, reviews with `approved` and a summary. It uses bounded
output, low temperature, validates paths and rejects malformed plans. It does not
assume native function calling. No provider output becomes an arbitrary shell
command. Compatibility with this HTTP shape is not a quality certification.

## FeatherLM assessment

Inspected upstream `engr-dr-ammad/FeatherLM`: README, inference routes, MIT license.
Its useful interfaces include OpenAI-style endpoints, capability metadata,
checkpoint loading, evaluation, LoRA and curated SFT helpers. No source or weights
are copied. Upstream states Nano 13.2M was trained on Tiny Shakespeare and does
not follow instructions; taught-answer rephrasing performance does not demonstrate
coding or general tool use. No coding evaluation of Nano was run here. Therefore
it is not assigned implementation work, even if its server accepts a chat request.
A future adapter must gate dispatch on signed/maintainer-reviewed evaluation
metadata rather than a model name alone. Current name gate is conservative and
not a cryptographic certification mechanism.

### Experimental FeatherLM probe (implemented, not run against weights here)

Start upstream FeatherLM on port 8003, then run:

```bash
FORGE_FEATHERLM_URL=http://127.0.0.1:8003/v1 \
FORGE_FEATHERLM_MODEL=runs/featherlm-nano/best \
python -m forge.featherlm
```

This separate adapter calls `/v1/completions` and records three small planning,
coding-format and tool-selection probes. It executes no generated code and grants
no tools. It always reports `implementation_eligible: false`: passing smoke probes
does not meet the held-out promotion gate. Configure authentication with
`FORGE_FEATHERLM_KEY` in the environment. No Nano weight evaluation is claimed here.

Optional explicit scaffolding: set `FORGE_STARTER=examples/starter/index.html` to
supply a behavior-free HTML form/list and implementation contracts to a coding
model. This improves grounding for small models. It is distinct from the complete
scripted fixture. A scaffold-assisted local run must be labeled as such; no
scripted implementation is substituted for model output.

### Recorded development weights

- Qwen2.5-Coder-1.5B-Instruct Q4_K_M SHA-256:
  `cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046`.
  Both unscaffolded and scaffold-assisted development runs exhausted bounded
  repairs without meeting the browser gate. It is not promoted as a working
  implementation model by these results.
- Final 7B trial: official Qwen2.5-Coder-7B-Instruct-GGUF revision
  `13fb94bfda8c8cf22497dc57b78f391a9acb426a`, Q2_K expected SHA-256
  `6ce2630974b0ef631e2b29064cd10a9cb16b278d001961d72bfd86987392c8d9`.
  This aggressive quantization is a constrained demonstration, not the recommended
  production quality setting. Recommended deployment remains 7B Q4 or higher.
  In this disk-limited environment weights are loaded with llama.cpp `--load-mode none` (older releases use `--no-mmap`)
  and the temporary download is removed after loading. Restarting the platform
  retains its database; restarting the inference server requires downloading the
  same pinned weights again. Ordinary installations should retain weights.

### Reproduce the actual llama.cpp demonstration

Use official llama.cpp CPU release b12322 and retain its CPU backend libraries.
Download the pinned 7B Q2_K file from:

`https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/13fb94bfda8c8cf22497dc57b78f391a9acb426a/qwen2.5-coder-7b-instruct-q2_k.gguf`

Verify the SHA-256 above, then start:

```bash
llama-server -m qwen2.5-coder-7b-instruct-q2_k.gguf \
  --alias qwen-coder-7b-local --host 127.0.0.1 --port 8081 \
  --load-mode none -c 8192 -t 3 -np 1
```

In another terminal, from FeatherForge (use a separate data directory from any
running dashboard):

```bash
FORGE_MODEL_URL=http://127.0.0.1:8081/v1 \
FORGE_MODEL=qwen-coder-7b-local \
FORGE_STARTER=examples/starter/index.html \
python -m tests.integration_demo --provider local --repair --data data-local-demo
```

The `--repair` flag explicitly authorizes at most two evidence-driven repair
attempts; omit it to stop at the first failed gate. In the recorded 7B run, no
implementation repair was needed. A later runtime restart required one explicit
review retry, without redoing successful implementation or QA. The full offline
continuation command is `python -m tests.resume_review --data <directory> --project
<id>`; stop the dashboard first because both commands acquire the same worker lock.
