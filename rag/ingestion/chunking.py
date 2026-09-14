"""Deterministic overlapping word windows, independent of an LLM."""

import hashlib
import json

from rag.ingestion.schemas import EvidenceChunk, EvidenceDocument


def chunk_document(
    document: EvidenceDocument, chunk_size: int = 80, overlap: int = 16
) -> list[EvidenceChunk]:
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Require chunk_size > overlap >= 0")
    words = document.content.split()
    provenance = document.model_dump(exclude={"content", "version"})
    chunks = []
    for index, start in enumerate(range(0, len(words), chunk_size - overlap)):
        text = " ".join(words[start : start + chunk_size])
        identity = json.dumps(
            [
                "words-v1",
                document.document_id,
                document.version,
                document.content_hash,
                chunk_size,
                overlap,
                index,
            ]
        )
        chunks.append(
            EvidenceChunk(
                **provenance,
                chunk_index=index,
                chunk_id=hashlib.sha256(identity.encode()).hexdigest(),
                document_version=document.version,
                text=text,
            )
        )
        if start + chunk_size >= len(words):
            break
    return chunks


def corpus_fingerprint(chunks: list[EvidenceChunk]) -> str:
    """Includes complete provenance, text and chunk configuration through stable IDs."""
    if not chunks or len({c.chunk_id for c in chunks}) != len(chunks):
        raise ValueError("Chunks must be nonempty and unique")
    data = [c.model_dump(mode="json") for c in sorted(chunks, key=lambda c: c.chunk_id)]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
