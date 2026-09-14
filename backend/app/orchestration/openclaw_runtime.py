"""OpenClaw 2026.9.4 headless adapter with a minimal, ephemeral pinned configuration."""

import json
import re
import tempfile
from pathlib import Path

from backend.app.db.base import utc_now
from backend.app.orchestration.cli import OpenClawCLI, RuntimeFailure, configured_agents, parse_json
from backend.app.orchestration.contracts import (
    AgentOutput,
    AgentTask,
    ErrorCategory,
    RuntimeMetadata,
)
from backend.app.orchestration.prompts import render_prompt
from backend.app.orchestration.registry import ROOT, AgentRegistry
from backend.app.orchestration.runtime import validate_findings


def safe_workspace(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path == ROOT or path.is_relative_to(ROOT) or ROOT.is_relative_to(path):
        raise RuntimeFailure(ErrorCategory.NOT_CONFIGURED)
    return path


def execution_config(agent_id: str, model: str, workspace: Path) -> dict:
    # No ambient config, provider keys, plugins, channels, includes, hooks or shell environment.
    return {
        "agents": {
            "defaults": {
                "systemAgent": {"agentId": agent_id},
                "skipBootstrap": True,
                "contextInjection": "never",
                "startupContext": {"enabled": False},
                "compaction": {"memoryFlush": {"enabled": False}},
            },
            "entries": {
                agent_id: {
                    "workspace": str(workspace),
                    "model": {"primary": model, "fallbacks": []},
                    "models": {model: {"agentRuntime": {"id": "openclaw"}}},
                    "skills": [],
                    "tools": {"deny": ["*"]},
                }
            },
        },
        "memory": {"search": {"enabled": False}},
        "tools": {"deny": ["*"], "codeMode": {"enabled": False}},
        "plugins": {"enabled": False},
        "skills": {"allowBundled": [], "load": {"extraDirs": [], "watch": False}},
        "logging": {"level": "silent", "consoleLevel": "silent"},
    }


def build_command(config: Path, workspace: Path, timeout: int) -> list[str]:
    return [
        "agent",
        "exec",
        "--config",
        str(config),
        "--cwd",
        str(workspace),
        "--message-file",
        "-",
        "--json",
        "--thinking",
        "off",
        "--code-mode",
        "direct",
        "--timeout",
        str(timeout),
    ]


class OpenClawRuntime:
    name = "openclaw"

    def __init__(self, registry: AgentRegistry, cli: OpenClawCLI | None = None):
        self.registry, self.cli = registry, cli or OpenClawCLI()

    def run(self, task: AgentTask) -> AgentOutput:
        started = utc_now()
        if self.registry.roles[task.role].agent_id != task.agent_name:
            raise RuntimeFailure(ErrorCategory.NOT_CONFIGURED)
        # Fail closed on unverified CLI versions; update compatibility tests before widening.
        if self.cli.version() != "2026.9.4":
            raise RuntimeFailure(ErrorCategory.UNAVAILABLE)
        agent = next((a for a in configured_agents(self.cli) if a["id"] == task.agent_name), None)
        if agent is None or not isinstance(agent.get("workspace"), str):
            raise RuntimeFailure(ErrorCategory.NOT_CONFIGURED)
        workspace = safe_workspace(Path(agent["workspace"]))
        if not workspace.is_dir():
            raise RuntimeFailure(ErrorCategory.NOT_CONFIGURED)
        status = self.cli.json(["models", "status", "--agent", task.agent_name, "--json"])
        model = status.get("resolvedDefault") if isinstance(status, dict) else None
        if not isinstance(model, str) or not re.fullmatch(
            r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_./:-]+", model
        ):
            raise RuntimeFailure(ErrorCategory.UNAVAILABLE)
        # Pinned config contains only a validated model identifier and our own safety controls.
        # Stored auth is discovered by OpenClaw for this named agent, never read/copied here.
        with tempfile.TemporaryDirectory(prefix="medtrust-exec-") as temporary:
            config = Path(temporary) / "config.json"
            config.write_text(json.dumps(execution_config(task.agent_name, model, workspace)))
            result = self.cli.execute(
                build_command(config, workspace, self.cli.timeout),
                render_prompt(task, self.registry),
            )
        if result.returncode == 2:
            raise RuntimeFailure(ErrorCategory.TIMEOUT)
        if result.returncode:
            raise RuntimeFailure(ErrorCategory.EXECUTION)
        envelope = parse_json(result.stdout)
        if (
            not isinstance(envelope, dict)
            or envelope.get("ok") is not True
            or envelope.get("status") != "ok"
        ):
            raise RuntimeFailure(ErrorCategory.EXECUTION)
        if not isinstance(envelope.get("final"), str):
            raise RuntimeFailure(ErrorCategory.INVALID_OUTPUT)
        for key in ("toolSummary", "bridgeCalls"):
            if key in envelope and not isinstance(envelope[key], dict):
                raise RuntimeFailure(ErrorCategory.INVALID_OUTPUT)
        # Any observable tool execution violates this phase's zero-tool contract.
        if envelope.get("toolSummary", {}).get("calls", 0) != 0:
            raise RuntimeFailure(ErrorCategory.EXECUTION)
        if any(
            envelope.get("bridgeCalls", {}).get(k, 0) != 0 for k in ("search", "describe", "call")
        ):
            raise RuntimeFailure(ErrorCategory.EXECUTION)
        findings = validate_findings(parse_json(envelope["final"]), task)
        return AgentOutput(
            **findings.model_dump(),
            started_at=started,
            completed_at=utc_now(),
            runtime_metadata=RuntimeMetadata(
                runtime="openclaw", model=model, provider=model.split("/", 1)[0]
            ),
        )
