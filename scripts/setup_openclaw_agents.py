"""Preview MedTrust agent creation. Only --apply creates missing agents/workspaces."""

import argparse
import json
import shlex
from pathlib import Path

from backend.app.core.config import Settings
from backend.app.orchestration.cli import (
    OpenClawCLI,
    RuntimeFailure,
    configured_agents,
    health_check,
)
from backend.app.orchestration.openclaw_runtime import safe_workspace
from backend.app.orchestration.registry import DEFINITIONS, AgentRegistry


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    result.add_argument(
        "--workspace-root", type=Path, default=Path.home() / ".openclaw" / "medtrust-agents"
    )
    return result


def setup(registry: AgentRegistry, cli: OpenClawCLI, root: Path, apply: bool = False) -> int:
    root = safe_workspace(root)
    if cli.version() != "2026.9.4":
        raise ValueError("Unverified CLI version")
    existing = {item["id"] for item in configured_agents(cli)}
    plans = []
    for definition in registry.roles.values():
        agent_id = definition.agent_id
        if agent_id in existing:
            print(f"{agent_id}: exists; unchanged (configuration is not certified by setup)")
            continue
        workspace = safe_workspace(root / agent_id)
        # Reject pre-existing paths including dangling symlinks, even during preview.
        if (root / agent_id).exists() or (root / agent_id).is_symlink():
            raise ValueError("Workspace already exists; manual review required")
        command = [
            "agents",
            "add",
            agent_id,
            "--non-interactive",
            "--workspace",
            str(workspace),
            "--json",
        ]
        print(shlex.join(["openclaw", *command]))
        print(f"  Create workspace role/policy files for {agent_id}; no auth or model changes.")
        plans.append((definition, workspace, command))
    if not apply:
        print("DRY RUN: no files, agents, authentication or configuration changed.")
        return 0
    # All paths are preflighted before mutation. Recheck roster immediately before each create.
    for definition, workspace, command in plans:
        if definition.agent_id in {item["id"] for item in configured_agents(cli)}:
            print(f"{definition.agent_id}: appeared during setup; skipped")
            continue
        workspace.mkdir(parents=True, exist_ok=False, mode=0o700)
        source = DEFINITIONS / "agents" / definition.role
        for name in ("IDENTITY.md", "role.json"):
            with (workspace / name).open("x", encoding="utf-8") as output:
                output.write((source / name).read_text(encoding="utf-8"))
        with (workspace / "AGENTS.md").open("x", encoding="utf-8") as output:
            output.write(definition.responsibility + "\n\n")
            for name in ("clinical_safety.md", "evidence_policy.md", "output_policy.md"):
                output.write((DEFINITIONS / "policies" / name).read_text(encoding="utf-8") + "\n")
        result = cli.execute(command)
        if result.returncode:
            # No automatic cleanup, overwrite, rollback, or agent deletion.
            print(
                "Creation failed; partial workspace may remain. Inspect manually before retrying."
            )
            return 1
        print(f"Created {definition.agent_id}; use only the MedTrust pinned-config runtime.")
    return 0


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        settings = Settings()
        cli = OpenClawCLI(timeout=settings.openclaw_timeout_seconds)
        print("OpenClaw version:", cli.version())
        if args.check:
            report = health_check(cli)
            print(json.dumps(report))
            return int(report["error"] is not None)
        return setup(AgentRegistry.load(settings), cli, args.workspace_root, args.apply)
    except (RuntimeFailure, OSError, ValueError):
        print(
            "Setup unavailable; check CLI version, registry and workspace paths. "
            "No repair attempted."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
