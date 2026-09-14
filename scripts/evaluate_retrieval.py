"""Opt-in live benchmark, or offline sparse/validation-only mode."""

import argparse
import json
from pathlib import Path

from backend.app.core.config import get_settings
from rag.evaluation.benchmark import evaluate, load_queries
from rag.retrieval.service import RetrievalService
from rag.retrieval.sparse import SparseRetriever
from rag.runtime import build_dense, load_chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--sparse-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dense = None
    try:
        settings = get_settings()
        documents, chunks = load_chunks(settings)
        queries = load_queries({d.document_id for d in documents})
        if args.validate_only:
            print(f"validated {len(queries)} evidence queries")
            return 0
        if not args.sparse_only:
            dense = build_dense(settings, chunks)
        service = RetrievalService(SparseRetriever(chunks), dense, settings.rag_rrf_constant)
        modes = ("sparse",) if args.sparse_only else ("sparse", "dense", "hybrid", "hybrid+rerank")
        results = evaluate(service, queries, modes)
        report = {
            "kind": "live-local" if dense else "local-sparse",
            "model": dense.encoder.identity if dense else None,
            "dimension": dense.encoder.dimension if dense else None,
            "collection": settings.qdrant_collection if dense else None,
            "documents": len(documents),
            "chunks": len(chunks),
            "corpus_fingerprint": service.sparse.fingerprint,
            "chunk_size": settings.rag_chunk_size,
            "overlap": settings.rag_chunk_overlap,
            "rrf_constant": service.fusion_constant,
            "candidate_limit": service.candidate_limit,
            "metrics": results,
        }
        for mode, values in results.items():
            print(f"Mode: {mode}")
            for name, value in values.items():
                print(f"{name}: {value}")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    except Exception as exc:
        print(f"Evaluation failed ({type(exc).__name__}); check model and indexed corpus.")
        return 1
    finally:
        if dense:
            dense.client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
