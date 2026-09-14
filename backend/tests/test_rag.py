"""Offline Phase 5 checks: no Docker, network, or downloaded model."""

import hashlib
import math
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient, models

from backend.app.core.config import Settings
from rag.embeddings.local import validate_vectors
from rag.evaluation.benchmark import BenchmarkQuery, evaluate, load_queries
from rag.evaluation.metrics import mean_reciprocal_rank, ndcg_at_k, recall_at_k, reciprocal_rank
from rag.ingestion.chunking import chunk_document, corpus_fingerprint
from rag.ingestion.loader import EXPECTED_IDS, load_synthetic_corpus
from rag.ingestion.schemas import EvidenceDocument, content_hash
from rag.reranking.lexical import rerank
from rag.retrieval.dense import DenseRetriever
from rag.retrieval.hybrid import fuse
from rag.retrieval.schemas import RetrievalResult
from rag.retrieval.service import RetrievalService
from rag.retrieval.sparse import SparseRetriever


class FakeEncoder:
    dimension = 8
    identity = "test-only-hashed-words-v1"

    def encode(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimension
            for word in text.lower().split():
                vector[hashlib.sha256(word.encode()).digest()[0] % self.dimension] += 1
            norm = math.sqrt(sum(x * x for x in vector))
            vectors.append([x / norm for x in vector])
        return vectors


@pytest.fixture
def documents():
    return load_synthetic_corpus()


@pytest.fixture
def chunks(documents):
    return [c for d in documents for c in chunk_document(d)]


def test_corpus_and_queries(documents, chunks):
    assert {d.document_id for d in documents} == EXPECTED_IDS
    assert len(documents) == 20
    assert len(chunks) == 40
    queries = load_queries(EXPECTED_IDS)
    assert len(queries) == 25
    assert set.union(*(q.relevant_document_ids for q in queries)) == EXPECTED_IDS
    assert all(d.source_type == "synthetic" and d.metadata["license"] == "MIT" for d in documents)


@pytest.mark.parametrize(
    "change",
    [
        {"content": " "},
        {"title": " "},
        {"source_type": "real_patient"},
        {"patient_name": "forbidden"},
        {"content_hash": "sha256:" + "0" * 64},
        {"retrieved_at": "2026-01-01T00:00:00"},
    ],
)
def test_document_validation(documents, change):
    with pytest.raises(ValidationError):
        EvidenceDocument.model_validate(documents[0].model_dump() | change)


def test_hash_canonicalization():
    assert content_hash("  cafe\u0301\n text ") == content_hash("café text")
    assert (
        content_hash("abc")
        == "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert content_hash("abc") != content_hash("ABC")


def test_chunking_windows_and_identity(documents):
    data = documents[0].model_dump(exclude={"content_hash"}) | {
        "content": "one two three four five six"
    }
    doc = EvidenceDocument.model_validate(data)
    chunks = chunk_document(doc, 4, 1)
    assert [c.text for c in chunks] == ["one two three four", "four five six"]
    assert chunks == chunk_document(doc, 4, 1)
    assert len({c.chunk_id for c in chunks}) == 2
    assert chunks[0].chunk_id != chunk_document(doc, 5, 1)[0].chunk_id
    changed = EvidenceDocument.model_validate(data | {"content": "one two three four five seven"})
    assert chunks[0].chunk_id != chunk_document(changed, 4, 1)[0].chunk_id
    assert len(chunk_document(doc, 6, 1)) == 1
    assert len(chunk_document(doc, 20, 0)) == 1


@pytest.mark.parametrize("size,overlap", [(0, 0), (4, 4), (4, -1), (4, 5)])
def test_bad_chunk_config(documents, size, overlap):
    with pytest.raises(ValueError):
        chunk_document(documents[0], size, overlap)


def test_fingerprint_and_sparse(chunks):
    assert corpus_fingerprint(chunks) == corpus_fingerprint(list(reversed(chunks)))
    sparse = SparseRetriever(chunks)
    results = sparse.search("creatinine renal", 5)
    assert results[0].document_id == "EVID-004"
    assert results[0].sparse_rank == 1
    assert sparse.search("zzzzzzzz", 5) == []
    assert results == sparse.search("creatinine renal", 5)
    with pytest.raises(ValueError):
        SparseRetriever(chunks + [chunks[0]])


def test_rrf_and_dedup(chunks):
    a, b = [RetrievalResult(**c.model_dump()) for c in chunks[:2]]
    result = fuse([a, a, b], [b, a])
    assert len(result) == 2
    assert all(r.fusion_score == pytest.approx(1 / 61 + 1 / 62) for r in result)
    assert [r.chunk_id for r in result] == sorted([a.chunk_id, b.chunk_id])
    assert fuse([a], [])[0].fusion_score == pytest.approx(1 / 61)
    with pytest.raises(ValueError):
        fuse([], [], 0)


def test_reranker(chunks):
    a = RetrievalResult(**chunks[0].model_dump(), fusion_score=0.01)
    b = RetrievalResult(**chunks[2].model_dump(), fusion_score=0.02)
    result = rerank("blood pressure", [b, a])
    assert result[0].chunk_id == a.chunk_id
    assert result[0].rerank_score > result[1].rerank_score
    assert a.rerank_score == 0


def test_known_metrics():
    ranking = ["x", "a", "b", "a"]
    relevant = {"a", "b", "c"}
    assert recall_at_k(ranking, relevant, 3) == pytest.approx(2 / 3)
    assert reciprocal_rank(ranking, relevant) == 0.5
    assert mean_reciprocal_rank([ranking, []], [relevant, relevant]) == 0.25
    assert ndcg_at_k(ranking, relevant, 3) == pytest.approx(
        (1 / math.log2(3) + 0.5) / (1 + 1 / math.log2(3) + 0.5)
    )
    assert ndcg_at_k(["a", "a", "b"], {"a", "b"}, 5) == 1
    assert recall_at_k([], relevant, 5) == ndcg_at_k([], relevant, 5) == 0
    with pytest.raises(ValueError):
        recall_at_k([], set(), 5)
    with pytest.raises(ValueError):
        ndcg_at_k([], relevant, 0)


def test_invalid_benchmark(tmp_path):
    with pytest.raises(ValidationError):
        BenchmarkQuery(query_id="x", query=" ", relevant_document_ids=[])
    path = tmp_path / "queries.json"
    path.write_text("[]")
    with pytest.raises(ValueError):
        load_queries(EXPECTED_IDS, path)
    with pytest.raises(ValueError):
        load_queries({"nonexistent"})


@pytest.mark.parametrize(
    "vectors,count,dim",
    [([[0, 0]], 1, 2), ([[float("nan"), 1]], 1, 2), ([[1, 2]], 2, 2), ([[1, 2]], 1, 3)],
)
def test_embedding_validation(vectors, count, dim):
    with pytest.raises(ValueError):
        validate_vectors(vectors, count, dim)


def test_qdrant_offline_pipeline_and_provenance(chunks, documents):
    client = QdrantClient(":memory:")
    dense = DenseRetriever(client, "test_evidence", FakeEncoder(), chunks)
    try:
        dense.ensure_collection()
        with pytest.raises(ValueError, match="incomplete"):
            dense.search("creatinine", 5)
        assert dense.upsert_chunks() == len(chunks)
        dense.ensure_collection()
        assert dense.upsert_chunks() == len(chunks)
        assert client.count("test_evidence", exact=True).count == len(chunks)
        service = RetrievalService(SparseRetriever(chunks), dense)
        originals = {c.chunk_id: c.model_dump() for c in chunks}
        for mode in ("dense", "sparse", "hybrid"):
            results = service.retrieve_evidence("creatinine renal", 5, mode)
            assert results
            for rank, result in enumerate(results, 1):
                assert result.final_rank == rank
                for key, value in originals[result.chunk_id].items():
                    assert getattr(result, key) == value
        results = evaluate(service, load_queries(EXPECTED_IDS))
        assert set(results) == {"sparse", "dense", "hybrid", "hybrid+rerank"}
        assert all(v["query_count"] == 25 for v in results.values())
        assert results == evaluate(service, load_queries(EXPECTED_IDS))
        mismatch = DenseRetriever(client, "test_evidence", FakeEncoder(), chunks[:-1])
        with pytest.raises(ValueError, match="incomplete"):
            mismatch.search("query", 5)
        with pytest.raises(ValueError, match="same corpus"):
            RetrievalService(SparseRetriever(chunks), mismatch)
    finally:
        client.close()


def test_mocked_collection_safety(chunks):
    client = Mock()
    client.collection_exists.return_value = True
    client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors=models.VectorParams(size=3, distance=models.Distance.DOT)
            )
        )
    )
    dense = DenseRetriever(client, "test", FakeEncoder(), chunks)
    with pytest.raises(ValueError):
        dense.ensure_collection()
    client.delete_collection.assert_not_called()
    client.create_collection.assert_not_called()
    client.get_collection.return_value.config.params.vectors = {
        dense.vector_name: models.VectorParams(size=8, distance=models.Distance.COSINE)
    }
    dense.ensure_collection(recreate=True)
    client.delete_collection.assert_called_once_with("test")
    client.create_collection.assert_called_once()


def test_service_validation_and_failure(chunks):
    service = RetrievalService(SparseRetriever(chunks))
    with pytest.raises(RuntimeError):
        service.retrieve_evidence("query")
    for query, k, mode in [
        (" ", 5, "sparse"),
        ("q", 0, "sparse"),
        ("q", 101, "sparse"),
        ("q", 5, "bad"),
    ]:
        with pytest.raises(ValidationError):
            service.retrieve_evidence(query, k, mode)
    assert service.retrieve_evidence("zzzzzzzz", 5, "sparse") == []


def test_settings_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_chunk_size=10, rag_chunk_overlap=10)


def test_app_import_without_qdrant():
    code = """
import sys
sys.modules['qdrant_client'] = None
sys.modules['sentence_transformers'] = None
from backend.app.main import app
assert app.title == 'MedTrust API'
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
