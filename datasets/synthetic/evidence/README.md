# Synthetic evidence corpus v1

Exactly 20 repository-authored synthetic educational documents, EVID-001–EVID-020,
released under the repository MIT license. No external guideline passages, textbook
text, patient records, diagnostic labels, treatment instructions or dosage guidance
were ingested. All dates are fixed fictional research metadata, not authority claims.

The 25 query labels are author-defined exploratory topic relevance judgments,
including paraphrases and multiple relevant documents. They are not independently
adjudicated clinical labels or a held-out medical benchmark. Do not tune on this
small fixture and claim general retrieval performance.

Content hashes cover NFC-normalized, whitespace-collapsed UTF-8 document content
only, excluding metadata. Chunk IDs include document ID, version, content hash,
word-window configuration and index. Snapshot fingerprints also cover all chunk
provenance. Hashes establish identity relative to a known value, not authenticity
or clinical trustworthiness. Null source dates remain null; no current timestamps
are invented. Free text and metadata still require eligibility review.

Retrieval relevance != clinical validity.
