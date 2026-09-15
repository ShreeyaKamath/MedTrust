# Phase 7: provenance-aware longitudinal clinical memory

MedTrust memory is a derived, fallible research representation of explicitly linked
clinical episodes. It is not an EHR, verified clinical truth, diagnosis, prescription,
or evidence of clinical effectiveness. Generated assertions are not clinical ground
truth. Human review remains mandatory.

## Architecture and identity

Clinical sources / validated agent outputs → host candidate construction → provenance
verification → temporal normalization → persistent memory and relationships →
confidence components and bounded selection → role-scoped context.

`ClinicalMemoryScope` has a UUID and unique `SYN-MEM-*` research label.
`MemoryEpisode` explicitly links existing ClinicalCase UUIDs to a scope. A case can
belong to one scope in Phase 7; a scope can contain multiple episodes. Membership is
never inferred from case-local `synthetic_patient_id`, demographics, similarity,
embeddings, or agent output. Existing clinical intake remains unchanged. Profile
fields are outside the initial memory field allowlist.

Five tables are added: `clinical_memory_scopes`, `memory_episodes`, `memory_entries`,
`memory_relationships`, and `memory_evidence`. The latter references existing
EvidenceRecord metadata. Models reuse Base, UUID, UTCDateTime, portable JSON, named
constraints, and RESTRICT foreign keys. Migration 0003 extends 0002; downgrading to
0002 drops memory tables while preserving clinical, run, evidence, and audit tables.

## Source facts and derived assertions

- **source_fact:** a host-created snapshot of one allowlisted persisted field. It
  preserves case UUID, source kind and row UUID, field, declared source type,
  normalized value, relevant semantic identity, source receipt time, event time,
  and digest. It references the original entity rather than cloning that entity.
  The service verifies existence, kind, field, case ownership, and membership.
- **derived_assertion:** a validated agent summary with producing AgentRun/role,
  runtime/prompt metadata, exact output digest, supporting source-fact IDs and/or
  supplied evidence. The persisted producing run must match the completed task.
  Its event time is unknown; no event time is invented for generated prose.

Only host code maps source paths and historical indexes to database IDs. Citation
membership and lineage do not prove semantic entailment of every summary statement.
Repeated citations are deduplicated by chunk. Metadata for the same captured
retrieval can be shared across assertions. Repeated assertions never become source
facts and never increase a corroboration score. Derived prose is not accepted as
independent support for another derived assertion; initial support edges run from
source facts to derived assertions.

### Canonicalization and idempotency

`memory-json-v1` uses UTF-8 JSON with sorted object keys and compact separators,
NFC strings, preserved whitespace and array order, ISO dates and UUIDs, and UTC
timezone-aware instants. Non-finite numbers and normalized key collisions are
rejected. Numeric `1`, numeric `1.0`, and string `"1"` retain their JSON representations;
this is not clinical numeric or unit equivalence. SHA-256 identifies the structured
snapshot. A unique scope/identity constraint prevents duplicate source ingestion.
Different source rows or episodes remain distinct even when values match.

Derived retry identity includes run, output digest, sources, and evidence snapshot
identity. Receipt-time changes alone do not create a new assertion on retry.
Evidence retains Phase 5 document hashes, chunk IDs, and corpus fingerprints. There
is no second document hashing algorithm, corpus, or vector index. Full chunk
provenance—including nullable source dates, document version, and metadata—is
preserved, with a separate host retrieval receipt time. Unavailable metadata stays
missing. The chunk must exactly match the supplied host corpus snapshot.

## Temporal semantics

| Time | Meaning |
| --- | --- |
| Event | Supplied observation, note authorship, or allergy timestamp; unknown when absent. |
| Source receipt | Existing source row creation timestamp, retained in provenance. |
| Availability | When the memory service accepts the entry using its host clock. |
| Created | Memory persistence metadata, stored separately even when initially equal to availability. |

Medication event anchors use the supplied end date for stopped records or start
date otherwise. Original date fields remain preserved; the service does not infer
a clinically effective interval. Precision is exactly unknown/date/datetime.
Unknown event time is never filled from ingestion time. Date-only values never
become invented midnight timestamps.

As-of selection requires entry creation, availability, and episode membership by
the cutoff. Known future events are excluded. Date-only events compare against the
cutoff's UTC calendar date. Unknown events remain eligible with explicit limitations.
Relationships apply only after their availability and endpoint eligibility.
The default clock is utc_now. An explicitly injected clock supports synthetic replay;
the demonstration labels its simulated 2030 receipt times.

## Conflict/correction lifecycle

Relationships are supports, contradicts, supersedes, and corrects. A correcting or
superseding entry points to its predecessor. Old rows remain stored. Cross-type
corrections cannot convert source facts to generated assertions. Self-links,
cross-scope links, and mixed correction/supersession cycles are rejected. Repeated
relationships return the existing relationship. Contradiction edges are symmetric
and stored once in canonical UUID order.

Automatic conflicts are limited to observation value fields with identical category,
name, coding metadata, unit, and exact event timestamp, but different non-null values.
There is no synonym matching, unit conversion, date-only conflict inference,
narrative interpretation, or medical adjudication. Different or unknown timestamps
do not produce automatic conflicts. Unmodeled collection context can still matter;
all flags require review. Explicit host-created contradiction relationships are supported.

Selection excludes applicable correction/supersession targets and derived entries
whose supporting facts are excluded. Active conflicts remain visible. Stale entries
can remain flagged historical context; age alone does not make a fact false. No
deletion API or automatic clinical conflict resolution is implemented.

## Memory-confidence components

These are deterministic experimental indicators, not calibrated probabilities.
There is no weighted aggregate. Memory confidence is not Agent Trust. Components
are recomputed at selection time and validated in [0,1]:

| Component | Definition and limitation |
| --- | --- |
| Source quality | 1 for directly verified source-field snapshots, 0 for generated assertions; an origin indicator, not medical source-quality validation. |
| Provenance completeness | 1 for entries passing mandatory lineage checks; invalid entries are excluded. Optional missing metadata is not fabricated. |
| Freshness | max(0, 1 − age_days / freshness_days) for known event times, 0 for unknown. Default horizon 365 days is configurable and experimental. |
| Temporal reliability | 1 for datetime, 0.5 for date, 0 for unknown: precision, not factual accuracy. |
| Consistency | 0 for an active recorded contradiction, 1 otherwise. Absence of detected conflict is not proof of consistency. |

## Selection and orchestration

Source snapshots are checked against current source rows; derived run, support,
and evidence links are validated. Changed, missing, or malformed provenance is
excluded. Old snapshots remain stored, but source edits can exclude them even for
an earlier as-of query. Full historical reconstruction requires versioned source
records, which Phase 4 does not provide.

Ordering is descending availability time, then deterministic identity digest.
Default limits are 20 entries (configurable 1–100) and 20,000 characters for the
complete serialized selection (configurable 1,024–100,000). Whole entries are omitted
instead of silently truncating clinical text. Output reports budget omissions,
excluded entries, and excess conflict references. This is a character budget, not
a tokenizer estimate; OpenClaw's independent byte cap still applies. Scope limits
are 10,000 entries and 30,000 relationships; oversized operations fail explicitly.

The global snapshot is bounded before role projection. History receives case,
condition, and note facts; lab receives observations; medication receives medication
and allergy facts. Derived summaries go to their producing role and review roles.
Critic/coordinator receive derived summaries rather than raw historical facts.
Role fairness across a full global budget is not optimized in Phase 7.

Construct MemoryIntegration(service, SelectionRequest(...)) and pass `memory=adapter`
to Orchestrator. Memory-enabled execution requires a matching persisted case and
explicit scope. The adapter captures source identities before minimization, complete
retrieval lineage, and accepted task/output pairs. After successful execution, call
`adapter.persist(result)`, then explicitly commit or roll back the caller's session.
The adapter already calls persist_run: do not persist the same run twice.

Compound persistence uses a savepoint. Source changes during execution abort it.
Failed/unbound results cannot create derived memory through the adapter. Unsupported
summaries without mapped support are not persisted as assertions. Memory-disabled
Phase 6 behavior, the six-role order, retrieval limits, and failure semantics remain.

Memory-enabled prompts separate SYSTEM_INSTRUCTIONS, CURRENT_CASE, RETRIEVED_EVIDENCE,
and HISTORICAL_MEMORY. Angle brackets in untrusted data are escaped. Historical
memory is a separate AgentTask field, never system instructions. Findings remain
schema 1.0 with a documented host memory-context extension. Historical references
use validated memory[INDEX] paths. Native OpenClaw memory search/flush, bootstrap,
startup context, plugins, skills, and tools remain disabled.

## Security and research limitations

Application code, its session, clock, corpus, and source mappings form the trusted
host boundary. Polymorphic clinical row references are validated by the service;
one generic UUID cannot express their SQL foreign keys. Direct SQL can bypass
application rules. PostgreSQL scope-row locks serialize cooperating writers; serial
SQLite tests do not establish equivalent concurrent behavior. Locks last until
the caller's transaction ends, including any model execution within that transaction.

History is application-preserved, not cryptographically immutable or tamper-proof.
Hashes detect mismatch, not authenticity. Untrusted text and prompt delimiters do
not establish model obedience. No authentication, MCP, clinical action, compliance,
or deployment claims are added. Tests use synthetic data only.

AuditEvent records IDs, hashes, counts, operation names, and fixed rejection reasons,
never clinical prose or prompts. Audits share caller transactions, so rollback also
removes audit events. There is no independently durable rejection ledger. Existing
Phase 6 crash-durability and host-compromise limitations remain.

## Reproducible checks and future evaluation

```bash
.venv/bin/python -m scripts.run_memory_scenario --validate-only
.venv/bin/python -m scripts.run_memory_scenario
.venv/bin/python -m pytest backend/tests/test_memory_contracts.py backend/tests/test_memory_persistence.py backend/tests/test_memory_temporal.py backend/tests/test_memory_orchestration.py
.venv/bin/python -m pytest
.venv/bin/ruff check backend memory rag scripts alembic
.venv/bin/ruff format --check backend memory rag scripts alembic
.venv/bin/python -m scripts.validate_local_postgres
```

The separate fixture covers ten software scenarios: stable fact, temporal change,
correction, contradiction, unknown time, stale history, derived evidence lineage,
cross-scope rejection, duplicate ingestion, and future-availability exclusion.
SQLite demonstration and temporary-schema PostgreSQL validation roll back writes.
Existing Phase 4/5 fixtures are unchanged. Software checks do not establish clinical
effectiveness. Future evaluation needs frozen source/corpus versions, episode-grouped
splits, temporal cutoffs, matched budgets, independent labels, and memory ablations.
Phase 8+ trust calibration, broader uncertainty, clinical semantic evaluation,
adversarial benchmarks, and gateway authorization remain deferred.
