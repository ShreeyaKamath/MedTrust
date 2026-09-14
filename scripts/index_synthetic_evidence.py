"""Run from root: uv run python -m scripts.index_synthetic_evidence."""

import argparse

from backend.app.core.config import get_settings
from rag.runtime import build_dense, load_chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--recreate", action="store_true", help="Explicitly delete this collection")
    args = parser.parse_args()
    if args.validate_only and args.recreate:
        parser.error("--validate-only and --recreate are mutually exclusive")
    try:
        settings = get_settings()
        documents, chunks = load_chunks(settings)
        print(f"documents loaded: {len(documents)}\nchunks generated: {len(chunks)}")
        if not args.validate_only:
            dense = build_dense(settings, chunks)
            try:
                dense.ensure_collection(recreate=args.recreate)
                print(f"chunks indexed: {dense.upsert_chunks()}")
            finally:
                dense.client.close()
    except Exception as exc:
        print(f"Indexing failed ({type(exc).__name__}); check corpus, model and Qdrant locally.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
