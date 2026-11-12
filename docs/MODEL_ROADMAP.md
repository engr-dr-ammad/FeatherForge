# Project-owned model roadmap

No training-data collection, online weight rewriting, self-promotion or automated
training deployment exists in milestone 1. They are separate from project memory.

1. **Project memory (implemented narrow version):** versioned scope, decisions,
   acceptance, checkpoints and source-linked verification facts. Retrieval stays
   within a project; incorrect facts can be superseded explicitly. Memory stores
   evidence; it is not a model-weight update.
2. **Reusable skills (planned):** maintainer-reviewed procedures with source,
   license, author consent, creation/review dates, compatible tool versions,
   applicability and regression tests. No automatic conversion of model output
   to trusted instructions. Revocation and version pinning are required.
3. **Offline learning (planned, opt-in):** explicit per-project contributor consent,
   provenance manifests, secret/PII removal, license compatibility review,
   deduplication and held-out split before any training export. Consent must be
   revocable before training; disclose limits of removal from already published
   weights. Separate memorized example answers from held-out generalization.

Build versioned coding, dependency-planning and tool-use suites before choosing a
base model. Include functional tasks, cancellation, prompt injection, malformed
tool outputs and secret handling. Keep held-out tasks private and disjoint by
repository and task family, not just random rows. Record failure categories,
latency, memory, test pass rates and task completion cost.

Start with licensed capable open-weight code models. Compare frozen baselines,
then fine-tune adapters on curated examples; consider training from scratch only
with evidence of scale, budget and a research hypothesis. Keep dataset hashes,
consent/license manifests, preprocessing commits, base-weight hash, adapter config,
training code, seed, hardware and full evaluation reports in a release registry.

Proposed promotion gate (requires a fixed minimum 100-task held-out suite): >=80%
functional coding pass, >=95% valid plans/tool schemas, zero unauthorized actions
or secret disclosure on the safety suite, no >2 percentage-point regression on
any protected baseline, and resource use within the declared hardware envelope.
These are proposed thresholds, not results already achieved. Require two human
maintainer approvals, reproducible evaluation and signed manifests. Canary a new
version behind an explicit configuration switch; pin prior adapter/weights and
provide one-step rollback. Agents cannot approve their own evaluations or promote
weights. FeatherLM remains research-only until it meets the same gates.
