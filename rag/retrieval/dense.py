"""Explicit Qdrant operations. No client/model construction at import or app startup."""

from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from rag.embeddings.local import Encoder, validate_vectors
from rag.ingestion.chunking import corpus_fingerprint
from rag.ingestion.schemas import EvidenceChunk
from rag.retrieval.schemas import RetrievalResult


class DenseRetriever:
    def __init__(
        self, client: QdrantClient, collection: str, encoder: Encoder, chunks: list[EvidenceChunk]
    ):
        self.client, self.collection, self.encoder = client, collection, encoder
        self.chunks = chunks
        self.fingerprint = corpus_fingerprint(chunks)
        self.vector_name = (
            "embedding_" + __import__("hashlib").sha256(encoder.identity.encode()).hexdigest()[:24]
        )
        self.scope = models.Filter(
            must=[
                models.FieldCondition(
                    key="corpus_fingerprint", match=models.MatchValue(value=self.fingerprint)
                )
            ]
        )

    def ensure_collection(self, recreate: bool = False) -> None:
        exists = self.client.collection_exists(self.collection)
        if exists and recreate:
            self.client.delete_collection(self.collection)
            exists = False
        if not exists:
            self.client.create_collection(
                self.collection,
                vectors_config={
                    self.vector_name: models.VectorParams(
                        size=self.encoder.dimension, distance=models.Distance.COSINE
                    )
                },
            )
        self.check_collection()

    def check_collection(self) -> None:
        vectors = self.client.get_collection(self.collection).config.params.vectors
        if not isinstance(vectors, dict) or set(vectors) != {self.vector_name}:
            raise ValueError("Collection embedding identity mismatch; use a new collection")
        params = vectors[self.vector_name]
        if params.size != self.encoder.dimension or params.distance != models.Distance.COSINE:
            raise ValueError("Collection dimension/distance mismatch")

    def upsert_chunks(self) -> int:
        # Validate all vectors before the first write. A failed batch remains incomplete;
        # search refuses incomplete snapshots. Re-running repairs the same stable IDs.
        vectors = self.encoder.encode([c.text for c in self.chunks])
        validate_vectors(vectors, len(self.chunks), self.encoder.dimension)
        self.check_collection()
        for start in range(0, len(self.chunks), 64):
            points = [
                models.PointStruct(
                    id=str(uuid5(NAMESPACE_URL, self.fingerprint + c.chunk_id)),
                    vector={self.vector_name: v},
                    payload={
                        "chunk": c.model_dump(mode="json"),
                        "corpus_fingerprint": self.fingerprint,
                    },
                )
                for c, v in zip(
                    self.chunks[start : start + 64], vectors[start : start + 64], strict=True
                )
            ]
            self.client.upsert(self.collection, points=points, wait=True)
        return len(self.chunks)

    def search(self, query: str, limit: int) -> list[RetrievalResult]:
        if limit < 1:
            raise ValueError("limit must be positive")
        self.check_collection()
        count = self.client.count(self.collection, count_filter=self.scope, exact=True).count
        if count != len(self.chunks):
            raise ValueError("Corpus snapshot missing/incomplete; index this corpus first")
        vector = self.encoder.encode([query])
        validate_vectors(vector, 1, self.encoder.dimension)
        # Exact search over this small research corpus; retrieve all ties before stable sorting.
        points = self.client.query_points(
            self.collection,
            query=vector[0],
            using=self.vector_name,
            query_filter=self.scope,
            limit=len(self.chunks),
            with_payload=True,
        ).points
        results = [
            RetrievalResult(
                **EvidenceChunk.model_validate(p.payload["chunk"]).model_dump(), dense_score=p.score
            )
            for p in points
        ]
        results.sort(key=lambda r: (-r.dense_score, r.chunk_id))
        return [r.model_copy(update={"dense_rank": i}) for i, r in enumerate(results[:limit], 1)]
