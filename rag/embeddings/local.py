"""Lazy CPU sentence-transformers adapter; tests inject an Encoder instead."""

import math
from typing import Protocol


class Encoder(Protocol):
    dimension: int
    identity: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


def validate_vectors(vectors: list[list[float]], count: int, dimension: int) -> None:
    if dimension < 1 or len(vectors) != count:
        raise ValueError("Embedding count or dimension mismatch")
    if any(
        len(v) != dimension or not all(math.isfinite(x) for x in v) or not any(x != 0 for x in v)
        for v in vectors
    ):
        raise ValueError("Embeddings must be finite, nonzero and match the dimension")


class LocalEncoder:
    def __init__(self, model_name: str, revision: str | None = None, batch_size: int = 32):
        import torch
        from sentence_transformers import SentenceTransformer

        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(1)
        self.model = SentenceTransformer(
            model_name, revision=revision, device="cpu", trust_remote_code=False
        )
        self.model.eval()
        dimension_method = getattr(self.model, "get_embedding_dimension", None)
        self.dimension = (
            dimension_method()
            if dimension_method is not None
            else self.model.get_sentence_embedding_dimension()
        )
        if not isinstance(self.dimension, int) or self.dimension < 1:
            raise ValueError("Model must declare an embedding dimension")
        self.identity = f"{model_name}@{revision or 'main'}:normalized:cpu"
        self.batch_size = batch_size

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import torch

        # Fail rather than silently truncate configurable chunks or long queries.
        tokens = self.model.tokenizer(texts, truncation=False, padding=False)["input_ids"]
        if any(len(row) > self.model.max_seq_length for row in tokens):
            raise ValueError("Input exceeds model token limit; reduce chunk/query length")
        with torch.inference_mode():
            vectors = self.model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            ).tolist()
        validate_vectors(vectors, len(texts), self.dimension)
        return vectors
