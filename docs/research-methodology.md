# Research methodology

## Research questions and hypotheses

Investigate whether provenance-aware memory reduces unsupported claims and memory poisoning, whether separately calibrated trust improves resilience to compromised agents, and whether uncertainty-guided retrieval improves evidence coverage and escalation at acceptable cost. These are hypotheses, not findings. The study evaluates a research decision-support prototype, not clinical efficacy or regulatory readiness.

## Baselines

| ID | Configuration | Incremental comparison |
| --- | --- | --- |
| B0 | Single LLM | No retrieval or multi-agent coordination |
| B1 | LLM + RAG | Add evidence retrieval |
| B2 | Multi-Agent + RAG | Add specialist coordination |
| B3 | Multi-Agent + RAG + Trust | Add evidence and agent trust assessment |
| B4 | Trust + Provenance Memory + Uncertainty | Extend B3 with provenance-aware memory, memory trust, and uncertainty-guided retrieval/escalation |
| B5 | Full MedTrust System | Extend B4 with integrated safety critic and zero-trust tool gateway |

All configurations retain the same research data restrictions and a safe local evaluation harness. B5's experimental gateway must be distinguished from containment controls that protect every baseline. B2–B4 use comparable specialist configurations; isolate the final safety critic in ablations to avoid confounding its effect with gateway enforcement. Fix the precise components before experiments.

## Experimental design

Use synthetic, permitted public de-identified, or properly de-identified cases with traceable dataset versions and eligibility review. Split development, calibration, and held-out evaluation by case and source; keep related longitudinal episodes together to reduce leakage. Keep held-out answers and judgments outside retrieval corpora. Freeze corpus snapshots, model versions/settings, prompts, seeds where supported, tool policies, and component settings. Tune thresholds only on development/calibration data.

Use the same base model, cases, evidence corpus, and tool availability where applicable. Record both equal-budget comparisons and actual resource use; differences in retrieval/tool availability are part of the specified baseline treatment. Pair clean and attacked versions of each case, vary attack severity and compromised-agent fraction, and repeat stochastic runs. Predefine exclusions, error handling, abstention scoring, and the primary endpoints (proposed: UCR and evidence correctness) before seeing held-out results.

Reference labels should be independently reviewed by qualified domain reviewers using frozen evidence and explicit rubrics; disagreements require adjudication and inter-rater agreement reporting. If clinical reviewers are unavailable, label results as exploratory and limit conclusions accordingly. Separate guideline agreement from clinical truth and document guideline version and applicability. Plan sample size using a pilot/power or precision analysis, not an invented target result.

## Metrics and operational definitions

Unsupported Clinical Claim Rate (UCR):

```text
UCR = unsupported clinical claims / total clinical claims
```

A clinical claim is an atomic, externally checkable clinical assertion in the report. Count claims lacking valid supporting evidence, including fabricated citations or non-entailing evidence, as unsupported. Assess at claim level with an adjudication rubric. For reports with no clinical claims, UCR is undefined (N/A), not zero; report abstention and coverage alongside micro-aggregated UCR and per-case distributions to prevent empty reports from appearing superior.

| Metric | Intended measurement |
| --- | --- |
| Task accuracy | Correct rubric-scored task outputs / eligible tasks; report coverage and abstentions separately |
| Evidence correctness | Evidence links judged valid, relevant, and supporting / evaluated evidence links |
| Guideline agreement | Applicable recommendations agreeing with the frozen guideline reference / applicable recommendations |
| Citation precision | Verifiable citations that support their linked claim / all supplied citations |
| Retrieval Recall@K | Relevant reference items retrieved in top K / all labeled relevant items |
| MRR | Mean reciprocal rank of first relevant result; zero for no hit |
| nDCG | Rank-discounted graded relevance normalized to ideal ranking at a declared cutoff |
| Agent disagreement | Fraction of comparable agent claim judgments that conflict, using a fixed rubric |
| Consensus accuracy | Correct consensus outputs / consensus-evaluable cases; report no-consensus cases |
| Trust calibration | Reliability of evidence, agent, and memory trust scores against their separately defined correctness labels |
| Expected Calibration Error (ECE) | Weighted absolute gap between confidence and empirical correctness in predeclared bins |
| Compromised-agent tolerance | Quality and safety degradation as the fraction of compromised agents increases |
| Unsafe action rate | Cases with a simulated policy-violating action / action-eligible cases; separately report attempted and executed actions |
| Prompt-injection success rate | Successful predefined attacker objectives / prompt-injection trials |
| Memory-poisoning success rate | Successful predefined attacker objectives / memory-poisoning trials |
| Tool-poisoning success rate | Successful predefined attacker objectives / tool-poisoning trials |
| False escalation rate | Unnecessary escalations / cases labeled as not needing escalation |
| Missed escalation rate | Cases not escalated / cases labeled as needing escalation |
| Latency | End-to-end wall time, including retrieval and escalation-request generation; exclude human response delay and disclose this |
| Token cost | Input/output token counts and monetary estimate under a recorded price schedule, if applicable |
| Retrieval time | Cumulative retrieval duration and per-call distribution with cache conditions recorded |
| Number of tool calls | Attempted, allowed, denied, failed, and retried calls per case |

Report undefined denominators as N/A with counts. ECE bins, retrieval K, relevance labels, safety rubrics, attack objectives, and cost accounting must be fixed before evaluation. Self-reported confidence and calibrated trust must have separate reliability plots. Metrics without an applicable component should be N/A, not artificially perfect.

## Analysis and reproducibility

Use paired comparisons on identical cases and case-level bootstrap confidence intervals; account for clustered episodes and repeated runs. Report effect sizes, distributions, failures, and multiplicity handling for secondary comparisons. Ablate provenance, trust channels, uncertainty-guided retrieval, critic, and gateway separately, including budget-matched controls. Publish permitted case definitions, configuration manifests, corpus versions, and aggregate results with traceable run IDs. Never fabricate results; no experiments or measured outcomes exist in Phase 1.

## Phase 5 retrieval-only benchmark

The fixed synthetic corpus has 20 repository-authored documents and 25 author-defined
queries, including paraphrases and multi-document labels. These are exploratory
software/topic judgments, not independent clinical adjudication or held-out medical
validation. No answer-generation labels are used. Retrieval relevance != clinical validity.

`scripts.evaluate_retrieval` compares sparse BM25, local dense retrieval, hybrid RRF,
and hybrid plus deterministic lexical reranking. Each mode uses the same corpus,
queries and candidate budget. Dense search is exact for this small corpus; ties sort
by stable chunk ID. Evaluation requests up to 100 chunks, collapses duplicate document
IDs preserving the first occurrence, then measures document-level rankings. MRR is
untruncated over that returned candidate pool (not necessarily the whole corpus when
larger than 100 chunks). Recall@1/@3/@5 and nDCG@5 use the deduplicated document ranks.

Recall@K = distinct relevant documents in top K / all labeled relevant documents.
MRR = mean reciprocal rank of the first relevant document, with zero for a miss.
Binary DCG@K = sum of 1/log2(rank+1) at relevant ranks, and nDCG@K divides by the
ideal DCG for min(K, number of relevant documents). Empty relevance sets are rejected
as undefined; empty retrieved rankings score zero. Repeated document chunks cannot
increase relevance credit. Report query count and all five aggregate metrics.

JSON output records corpus fingerprint, model identity/revision, dimension, collection,
chunk settings, candidate budget, fusion constant and whether the run is live-local
or local-sparse. Store generated results in the ignored experiment results directory.
Offline tests use deterministic fake embeddings and Qdrant's in-memory client only;
those checks are not real-model benchmark evidence. Freeze dependency lock, corpus,
queries and model revision for repeat runs. Numerical reproducibility across different
hardware/library versions is not guaranteed by inference mode alone. No clinical
performance claim follows from these small corpus metrics.
