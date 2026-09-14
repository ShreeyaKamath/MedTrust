# Research threat model

## Scope, assets, and adversaries

This model describes future controls for a local research prototype. Protect case confidentiality, evidence and memory integrity, tool authorization, report reliability, and audit integrity. Treat case text, external evidence, agent outputs, memory entries, and MCP responses as untrusted. An adversary may control an input document, retrieved content, one or more simulated specialist outputs, or a local mock tool response. Orchestrator, identity, policy, and audit compromise are residual risks requiring separate hardening; this design does not claim protection against a fully compromised host.

## Threats and proposed controls

| Threat | Boundary / potential failure | Proposed control and evaluation signal |
| --- | --- | --- |
| Direct prompt injection | Intake text attempts to override instructions | Separate data from policy; reject authority changes; measure attacker-objective success |
| Indirect prompt injection | Clinical note or tool response introduces instructions | Treat external text as data; enforce scoped tool permissions; measure propagation and denied calls |
| Poisoned retrieved documents | Retrieval introduces false or malicious evidence | Source validation, corroboration, provenance checks; measure unsupported claims and attack success |
| Stale evidence | Old guidance is treated as current | Version/freshness metadata and applicability review; flag outdated support |
| Compromised specialist agent | Agent fabricates findings or requests privileges | Authenticate identity but independently verify claims; isolate capabilities; measure degradation by compromised fraction |
| Hallucinated evidence | Fabricated citation or non-entailing passage | Resolve citations and assess support; measure citation precision and UCR |
| Unauthorized MCP/tool calls | Agent accesses an ungranted operation or resource | Authorize each call, deny by default; count attempted and executed violations |
| Excessive agent confidence | Confidence suppresses needed review | Keep confidence separate from trust and uncertainty; measure calibration and missed escalation |
| Corrupted longitudinal memory | Poisoned derived entries persist | Trace source lineage, validate corrections, quarantine unverifiable entries; measure poisoning success |
| Contradictory patient history | Conflicts are silently merged | Preserve timestamps and conflicting assertions; evaluate conflict detection and escalation |
| Privilege escalation attempts | Delegation expands identity scope | Non-transferable scoped permissions and operation-level checks; measure blocked scope changes |
| External data exposure | Tool arguments, logs, or egress leak sensitive content | Sensitivity classification, minimization, destination restrictions and redaction; use synthetic exposure markers |
| Unsafe tool execution | Tool effects exceed authorized scope | Initially read-only mock capabilities, argument validation, sandboxing and explicit approval for future high-risk actions |
| Provenance manipulation | Forged lineage makes evidence appear reliable | Verify origin/version and integrity independently; audit lineage changes; test forged references locally |

Controls are planned, not implemented. Detection alone is insufficient: independent enforcement must contain the effects of missed detections. Correlated sources, identity theft, de-identification failures, reviewer error, and incomplete threat coverage remain limitations.

## Zero-trust principles

- Authenticate every agent; identity does not establish clinical reliability.
- Authenticate every tool; authenticated responses still require validation.
- Authorize each operation against identity, resource, arguments, and context.
- Grant least privilege and deny by default, including unknown capabilities.
- Handle data sensitivity explicitly in intake, storage, retrieval, egress, and logs.
- Use uncertainty-sensitive authorization: greater uncertainty can restrict or escalate permission, never expand it automatically.
- Audit every privileged action and attempted violation without secrets, patient identifiers, or private chain-of-thought.
- Require human approval for irreversible/high-risk future actions, tied to a specific operation and subject to independent policy checks.

## Future gateway decisions

| Decision | Meaning |
| --- | --- |
| ALLOW | Permit a policy-authorized operation with baseline privileged-action auditing |
| ALLOW_AND_AUDIT | Permit with additional review metadata and monitoring |
| REQUIRE_HUMAN_APPROVAL | Hold execution pending explicit approval; revalidate identity, scope, and policy before execution |
| DENY | Block execution and record a minimal reason; agents cannot override this outcome |

Initial MCP tools are **read-only**, restricted to approved research resources. A read can still expose data, so resource scope and egress remain enforced. No clinical writes, prescriptions, external communications, or arbitrary execution are enabled. Future approval pathways do not imply that such capabilities are currently supported.

## Evaluation containment

Use local synthetic/de-identified cases and mock agents/tools. Never attack real healthcare systems or use real patient records. Record structured findings and concise policy reasons, not internal reasoning traces. Phase 1 contains no attack payloads, running tools, or implemented mitigations.
