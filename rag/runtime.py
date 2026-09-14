"""Explicit composition shared by opt-in scripts, never imported by FastAPI."""

from backend.app.core.config import Settings
from rag.ingestion.chunking import chunk_document
from rag.ingestion.loader import load_synthetic_corpus


def load_chunks(settings: Settings):
    documents = load_synthetic_corpus()
    chunks = [
        chunk
        for document in documents
        for chunk in chunk_document(document, settings.rag_chunk_size, settings.rag_chunk_overlap)
    ]
    return documents, chunks


def build_dense(settings: Settings, chunks):
    from qdrant_client import QdrantClient

    from rag.embeddings.local import LocalEncoder
    from rag.retrieval.dense import DenseRetriever

    encoder = LocalEncoder(settings.embedding_model, settings.embedding_revision)
    client = QdrantClient(url=settings.qdrant_url or "http://127.0.0.1:6333", timeout=15)
    return DenseRetriever(client, settings.qdrant_collection, encoder, chunks)
