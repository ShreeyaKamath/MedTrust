"""Load reviewed local JSON evidence; no scraping or network ingestion."""

from pathlib import Path

from rag.ingestion.schemas import EvidenceDocument

CORPUS = Path(__file__).resolve().parents[2] / "datasets/synthetic/evidence"
EXPECTED_IDS = {f"EVID-{i:03}" for i in range(1, 21)}


def load_documents(path: Path = CORPUS) -> list[EvidenceDocument]:
    documents = [
        EvidenceDocument.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(path.glob("*.json"))
    ]
    if not documents or len({d.document_id for d in documents}) != len(documents):
        raise ValueError("Corpus must contain unique, nonempty documents")
    return documents


def load_synthetic_corpus(path: Path = CORPUS) -> list[EvidenceDocument]:
    documents = load_documents(path)
    if {d.document_id for d in documents} != EXPECTED_IDS:
        raise ValueError("Expected exactly EVID-001 through EVID-020")
    if any(d.source_type != "synthetic" or d.metadata.get("license") != "MIT" for d in documents):
        raise ValueError("Expected reviewed synthetic MIT research evidence")
    return documents
