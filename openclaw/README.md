# OpenClaw orchestration foundation — Phase 6

Repository definitions are research-role instructions, not autonomous clinicians or
private agent memory. Use the MedTrust runtime to execute them; registering an agent
alone does **not** enforce its tool policy for other OpenClaw entry points.

## Local use

```bash
openclaw --version
uv run python -m scripts.setup_openclaw_agents --dry-run
uv run python -m scripts.setup_openclaw_agents --check
uv run python -m scripts.run_agent_orchestration --case-id CASE-001 --runtime mock
uv run python -m scripts.run_agent_orchestration --case-id CASE-001 --runtime openclaw --dry-run
```

The runner loads the committed Phase 4 fixture by external ID, without PostgreSQL.
Its default retrieval mode is explicitly `sparse`, using the Phase 5 service and
committed corpus without internet, embeddings, or Qdrant. Select `--retrieval-mode
hybrid` or `dense` explicitly when the Phase 5 infrastructure is available. There is
no fallback from hybrid to sparse or from OpenClaw to mock. The runtime setting
`MEDTRUST_AGENT_RUNTIME` defaults to `mock`; `--runtime` overrides it.

Mock outputs are deterministic inventories of supplied data and are visibly marked
`runtime=mock`. Their timestamps are fixed at 2000-01-01 UTC. Run IDs and actual
workflow trace timestamps are host-generated, so separate orchestration traces are
not byte-identical. No semantic clinical evaluation is simulated.

## Setup and live prerequisites

The setup helper defaults to dry-run. `--check` performs read-only health inspection.
`--apply` is the sole mutation opt-in. Review the printed plan before running:

```bash
uv run python -m scripts.setup_openclaw_agents --apply
```

Apply only creates missing `medtrust-*` agents and new external workspaces. It uses
`openclaw agents add ID --non-interactive --workspace PATH --json`, with no model,
authentication, routing or deletion flags. It does not overwrite existing agents or
workspaces, never deletes anything, and does not copy credentials. All intended paths
are checked before writing; the roster is rechecked before each create. A failure can
leave a newly created workspace or partial agent batch; inspect manually, do not
retry by deleting user data. These checks are not protection against a hostile local
process racing filesystem changes.

Workspace roots default to `Path.home() / '.openclaw' / 'medtrust-agents'` and can be
changed using `--workspace-root`. Repository paths and their ancestors are rejected.
The helper installs identity, role and embedded policy text in new workspaces. These
files are never used as longitudinal memory. Existing agent configuration remains
unmodified; review it separately if using that agent outside MedTrust.

Live execution requires an installed compatible CLI, an existing named agent and
workspace, a resolved model, and usable authentication already managed by OpenClaw.
No login is initiated. No provider keys appear in repository configuration. Provider
failure is a failed run, not permission to configure credentials automatically.

## Verified CLI boundary

Compatibility was inspected against **OpenClaw 2026.9.4 (3a9d69d)**. The adapter fails
closed on other versions until its config/envelope compatibility is revalidated.
The installed `agent exec` has **no `--agent` option**. Agent selection uses a temporary
pinned config with `agents.defaults.systemAgent.agentId` and `agents.entries`.
The model identifier comes from `models status --agent ID --json` (`resolvedDefault`).
No commercial model is hard-coded.

Execution uses an argv list:

```text
openclaw agent exec --config TEMP_CONFIG --cwd EXTERNAL_WORKSPACE
  --message-file - --json --thinking off --code-mode direct --timeout 60
```

The adapter pins the built-in `openclaw` harness for the resolved model to keep tool
denials under the inspected runtime. It does not inherit ambient provider endpoint
configuration, plugins, harness selection, fallback chains, hooks or tool grants.
Custom providers needing ambient endpoints/headers and plugin-only providers are
therefore outside this initial compatibility scope; configure/support them explicitly
in a later reviewed adapter change. Stored auth discovery remains OpenClaw's concern;
MedTrust never reads or copies credential files or ambient config.

The pinned config denies `*` globally and per agent, uses empty skill allowlists,
disables plugins, Code Mode, memory search, memory flush, startup context and bootstrap
injection. It supplies all role/policy instructions directly in the prompt because
exec skips workspace bootstrap. No `--state-dir` is supplied: OpenClaw owns temporary
session state. OpenClaw may retain temporary state after abnormal cleanup; host-level
retention and provider internals are outside MedTrust's guarantees. MedTrust never
requests, parses or persists private reasoning payloads.

The stable exec envelope uses `ok`, `status`, and `final`; only `final` is interpreted
as agent JSON. Payloads and arbitrary provider diagnostics are not retained. Observable
tool calls cause failure; optional tool telemetry absence is not proof of no tool use.
Structured findings are validated for schema, invocation identity and exact citation
membership. These checks do not prove factual entailment or clinical safety of free
text. Prompt boundaries are defense in depth, not a prompt-injection prevention claim.
Human review remains mandatory.

The POSIX subprocess transport uses no shell, passes the prompt through stdin rather
than argv, bounds combined stdout/stderr to 1 MiB, caps prompt bytes at 1 MiB, and
applies a configurable 1–600 second deadline per CLI command (default 60). It kills the
process group on timeout, overflow or interruption. Raw stderr is captured and discarded.
Non-POSIX execution fails closed. No retries or recursive agent loops are implemented.
The fixed workflow allows six role invocations, up to nine unique evidence questions,
and at most five retrieved chunks per question. Oversized context fails rather than
silently truncating clinical data. The existing retrieval service owns its own timeouts.

Official references: [agent exec](https://docs.openclaw.ai/cli/agent#agent-exec),
[agent management](https://docs.openclaw.ai/cli/agents), and
[configuration](https://docs.openclaw.ai/gateway/configuration-reference).
Local installed help/source and read-only config validation are the compatibility
basis when documentation differs.

## Service and audit use

`backend.app.orchestration.workflow.Orchestrator` accepts either a Phase 4 create
request (fixture case ID is null) or `ClinicalCaseDetailResponse` (stored UUID).
It validates eligibility again and returns structured outputs plus a metadata-only
trace. No HTTP endpoint is added: explicit local service composition avoids exposing
live model execution through the currently unauthenticated research API.

`persist_run(session, result)` explicitly reuses Phase 3 `AgentRun` and `AuditEvent`
for stored cases. The caller commits or rolls back. It stores hashes, counts, state
transitions, retrieval metadata, safe errors and timestamps, never generated prose or
full prompts. Audit events are accumulated during execution and persisted afterward;
process crashes before persistence can lose the in-memory trace. This is not a durable
workflow engine or tamper-evident audit implementation. No schema migration is needed.

## Offline validation

```bash
uv run pytest backend/tests/test_orchestration.py
uv run pytest
uv run ruff check backend rag scripts openclaw alembic
uv run ruff format --check backend rag scripts alembic
```

`openclaw/` contains Markdown, JSON and text only. Ruff directory discovery skips
those assets; they are not Python lint inputs. Unit tests mock CLI discovery and
subprocess execution. Live checks are separate and never run from pytest.

No Phase 7 clinical behavior, trust scoring, uncertainty engine, longitudinal memory,
MCP, frontend, attack framework, consensus algorithm or clinical action is implemented.
