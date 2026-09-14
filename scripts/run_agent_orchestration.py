"""Run a committed synthetic fixture through the Phase 6 application service."""

import argparse
import json

from backend.app.core.config import Settings
from backend.app.orchestration.cli import OpenClawCLI
from backend.app.orchestration.mock import MockAgentRuntime
from backend.app.orchestration.openclaw_runtime import OpenClawRuntime
from backend.app.orchestration.registry import AgentRegistry
from backend.app.orchestration.workflow import Orchestrator
from rag.retrieval.service import RetrievalService
from rag.retrieval.sparse import SparseRetriever
from rag.runtime import build_dense, load_chunks
from scripts.seed_synthetic_cases import load_dataset


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-id", required=True, help="Committed fixture external ID, e.g. CASE-001"
    )
    parser.add_argument("--runtime", choices=("mock", "openclaw"))
    parser.add_argument("--retrieval-mode", choices=("sparse", "dense", "hybrid"), default="sparse")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = Settings()
        runtime_name = args.runtime or settings.agent_runtime
        print("MOCK RUN" if runtime_name == "mock" else "LIVE OPENCLAW RUN")
        registry = AgentRegistry.load(settings)
        case = next(
            (case for case in load_dataset() if case.external_case_id == args.case_id), None
        )
        if case is None:
            print("Synthetic fixture not found.")
            return 1
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "dry_run": True,
                        "roles": list(registry.roles),
                        "retrieval_mode": args.retrieval_mode,
                    }
                )
            )
            return 0
        _, chunks = load_chunks(settings)
        dense = build_dense(settings, chunks) if args.retrieval_mode != "sparse" else None
        retrieval = RetrievalService(SparseRetriever(chunks), dense, settings.rag_rrf_constant)
        runtime = (
            MockAgentRuntime()
            if runtime_name == "mock"
            else OpenClawRuntime(registry, OpenClawCLI(settings.openclaw_timeout_seconds))
        )
        result = Orchestrator(runtime, registry, retrieval, args.retrieval_mode).run(case)
        # Print metadata only; structured findings are available to service callers.
        print(
            json.dumps(
                {
                    "orchestration_id": str(result.orchestration_id),
                    "case_id": args.case_id,
                    "status": result.status,
                    "runtime": runtime_name,
                    "roles": [output.role for output in result.outputs],
                    "evidence_ref_count": len(result.evidence_refs),
                    "requires_human_review": result.requires_human_review,
                    "trace": result.trace.model_dump(mode="json"),
                },
                indent=2,
            )
        )
        return 0 if result.status == "completed" else 1
    except Exception:
        print("Orchestration unavailable; verify fixture, runtime and retrieval configuration.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
