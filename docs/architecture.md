# Proposed research architecture

The clinical pipeline below remains proposed. Phase 1 established documentation and scaffolding; Phase 2 added the FastAPI foundation; Phase 3 implements only the persistence layer described below.

## Governing distinctions

- **LLM reasoning != clinical evidence:** generated analysis cannot serve as its own supporting source.
- **LLM memory != authoritative patient record:** memory is a derived, fallible research representation; source records remain distinct.
- **Agent confidence != trust:** self-reported confidence is an output to calibrate, not an authorization signal or independent reliability estimate.
- **Agent recommendation != authorization:** only an independently enforced operation policy can permit a tool action.

No private chain-of-thought will be requested for storage, exposed, or logged. Observable artifacts are structured findings, short evidence-grounded summaries, and policy decision reasons.

## Pipeline and boundaries

Clinical Case Intake → Input Safety / PII Gate → OpenClaw Orchestrator → Specialist Agents → Evidence Retrieval + Provenance-Aware Memory → Trust Engine → Uncertainty Engine → Safety Critic / Zero-Trust Gate → Clinician-Facing Evidence Report.

This is the conceptual reporting sequence. Retrieval may recur under a bounded uncertainty policy. The tool gateway mediates every call throughout the sequence, not just at the final gate. Inputs, retrieved documents, memory, agent messages, and tool responses cross separate trust boundaries and never carry implicit authority.

## Clinical Case Intake

Accept only synthetic, public appropriately de-identified, or properly de-identified research cases. Preserve a case identifier, source reference, event times, units, and missing fields without filling gaps with invented facts. Separate reported history from verified observations. Intake is not diagnosis or an authoritative record editor.

## Input Safety / PII Gate

Check data eligibility, identifiers, malformed content, and untrusted embedded instructions before agent processing. Reject or quarantine disallowed inputs; minimize retained data and redact audit metadata. Treat clinical narrative as data, never as system instructions. Detection is imperfect and complements dataset governance rather than replacing it.

## OpenClaw Orchestrator

The future orchestrator will coordinate specialist assignments, bounded retries, retrieval budgets, and report assembly. It will propagate scoped identity and case context and enforce structured output contracts. It must not promote agent consensus into evidence or confer tool privileges through task delegation. Integration details remain undecided.

## Specialist agents

| Agent | Intended responsibility |
| --- | --- |
| History Agent | Organize reported history, temporal relationships, missing information, and contradictions |
| Lab Agent | Summarize supplied laboratory observations with units, source references, and contextual limitations |
| Medication Agent | Reconcile supplied medication information, timestamps, and inconsistencies; no prescribing or execution |
| Guideline Agent | Retrieve applicable guideline passages, versions, and applicability limitations |
| Evidence / Research Agent | Retrieve and compare supporting and conflicting research evidence |
| Critic Agent | Challenge unsupported claims, source mismatches, contradictions, and unsafe report content |

Each output will contain claims, evidence, citations/provenance, missing information, contradictions, confidence, and limitations. A concise evidence-grounded finding is sufficient; internal reasoning traces are excluded. The Critic Agent provides analysis; it cannot replace the independent policy enforcement gateway.

## Evidence retrieval

Future ingestion, embeddings, retrieval, and reranking will retain source identifiers, publication/version dates, retrieval times, passages, and applicability metadata. Retrieval will seek disconfirming as well as supporting evidence. Source quality, freshness, and entailment must be assessed separately from retrieval rank. A high similarity score is not evidence correctness. Untrusted document instructions must not affect policies or tool authority.

## Provenance-aware memory

Longitudinal memory will preserve the lineage of each derived finding: research case ID, source reference and version, event time, ingestion time, producing agent/version, evidence links, and supersession/correction relationships. Derived claims must remain distinguishable from source observations. Conflicting entries will be retained with explicit conflict status instead of silently overwritten. Stale or unverifiable entries should be excluded from reliance or flagged for review. Retention, access, and deletion policies will apply to memory and audit records alike.

## Trust engine

Assess three separate concepts: evidence trust (quality, freshness, provenance and applicability), agent trust (independently measured reliability and policy compliance), and memory trust (lineage integrity, corroboration and freshness). Do not infer reliability from confidence, fluency, consensus, or repeated copies of the same source. Track dependent evidence to avoid double counting. Trust estimates need uncertainty and calibration against held-out labels; formulas, aggregation, and thresholds are future research decisions.

## Uncertainty engine

Estimate uncertainty from missing information, contradictions, evidence insufficiency, disagreement, and calibration signals. Thresholds will be selected on development data and frozen before held-out evaluation.

| Level | Intended behavior |
| --- | --- |
| LOW | Proceed to clinician-facing evidence report, with limitations and mandatory clinician review |
| MEDIUM | Retrieve more evidence and/or perform additional structured reasoning within a fixed budget |
| HIGH | Escalate to human review / request additional information; withhold unsupported conclusions |

When additional retrieval fails or budgets are exhausted, report unresolved uncertainty and escalate. Low uncertainty never bypasses authorization or implies clinical correctness.

## Safety critic and clinician report

The final safety review will check evidence support, contradictory findings, unsupported claims, missing context, and policy compliance. The report will show structured findings, traceable evidence, uncertainty, limitations, and escalation status. Recommendations require clinician review. Reports are informational artifacts and confer no permission to act.

## Zero-trust tool gateway

Future MCP access is authenticated, least-privilege, deny-by-default, and initially read-only. Authenticate agents and tools, authorize each operation against identity, resource, sensitivity, and uncertainty, validate arguments, and treat responses as untrusted data. Gateway outcomes are ALLOW, ALLOW_AND_AUDIT, REQUIRE_HUMAN_APPROVAL, or DENY. Every privileged operation is audited, including ALLOW; ALLOW_AND_AUDIT requests enhanced review metadata. Approval does not override a denied capability. No write or execution capability exists in this phase; future irreversible/high-risk capabilities require explicit human approval tied to the precise operation and separate policy authorization.

## Audit and evaluation pipeline

Record research case/run IDs, component and policy versions, source references, structured outputs, gateway outcomes, escalation events, and timing/cost metadata. Exclude secrets, real patient information, and private chain-of-thought. Keep audit access scoped and make integrity changes detectable. Evaluation will replay frozen cases and local adversarial scenarios, associate outputs with independent labels, and report component failures as well as aggregate scores. Phase 3 supplies audit record storage; integrity enforcement mechanisms remain deferred.

## Phase 3 persistence foundation

SQLAlchemy 2.x typed models share declarative metadata with a reversible Alembic
migration. PostgreSQL with synchronous psycopg 3 is the local persistence target;
SQLite supports isolated model and migration tests. Settings supply `DATABASE_URL`,
kept out of settings representations. Engine creation is lazy and SQL parameter
logging is disabled. App import, startup and `/health` do not connect to a database.

- **ClinicalCase** stores a unique research case reference, title, summary, eligible
  source type, de-identification flag and timestamps. Only synthetic/de-identified
  source values and a true de-identification flag are accepted. These declarations
  do not prove that free text is de-identified; eligibility review remains required.
- **AgentRun** links to one case and records observable execution metadata and concise
  output summaries. Pending runs have nullable `started_at`; completion time is also
  nullable. No execution, state machine or hidden chain-of-thought storage exists.
- **EvidenceRecord** stores source references, publication/retrieval dates, a caller
  supplied content hash (use an algorithm-prefixed value such as `sha256:...`) and
  provenance JSON. A nullable case link permits shared source metadata. No documents
  are ingested, no hashes are computed, and no provenance/trust scoring is implemented.
- **AuditEvent** records actor/action/outcome and optional case/run/resource references.
  Nullable links support system-level events. When both case and run are supplied,
  callers must keep their case association consistent; cross-link enforcement is deferred.

Cases have many runs, evidence records and audit events; runs have many audit events.
Foreign keys use RESTRICT, with no cascading deletes or automatic reference nulling,
so parent deletion cannot silently erase or detach history. Audit rows have only a
creation timestamp and no update schema: append-only use is a convention at this
stage, not database-enforced immutability. Controlled retention/deletion policies and
append-only database permissions are future work. JSON changes should replace the
whole value; in-place nested mutation tracking is not configured.

All four entities are research artifacts, **not authoritative EHR records**. No direct
PII columns are present; schema tests guard against obvious identifiers. Free-text
and JSON fields are not PII detectors. `AuditEvent.details` must contain safe structured
metadata only: no secrets, API keys, OAuth tokens, full prompts containing sensitive
records, sensitive patient data or hidden chain-of-thought. The same restrictions
apply to summaries, references, error messages and provenance metadata. Never log
records, connection URLs or database exception details. No public CRUD endpoints,
external clinical connections or later-phase functionality are introduced.
