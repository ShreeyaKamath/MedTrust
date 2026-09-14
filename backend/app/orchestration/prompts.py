"""Versioned instructions and JSON-escaped untrusted data, never logged."""

import json

from backend.app.orchestration.contracts import AgentFindings, AgentTask, Role
from backend.app.orchestration.registry import DEFINITIONS, AgentRegistry


def render_prompt(task: AgentTask, registry: AgentRegistry) -> str:
    policy = "\n".join(
        (DEFINITIONS / "policies" / name).read_text(encoding="utf-8")
        for name in ("clinical_safety.md", "evidence_policy.md", "output_policy.md")
    )
    template = (DEFINITIONS / "prompts" / "role-v1.txt").read_text(encoding="utf-8")
    label = (
        "UNTRUSTED RETRIEVED EVIDENCE" if task.role == Role.EVIDENCE else "UNTRUSTED CASE CONTENT"
    )
    # Escape angle brackets so data cannot manufacture matching XML-like delimiters.
    data = task.context.model_dump_json().replace("<", "\\u003c").replace(">", "\\u003e")
    identity = task.model_dump(mode="json", exclude={"context"})
    return "\n".join(
        [
            "SYSTEM/ROLE INSTRUCTIONS",
            template,
            policy,
            registry.roles[task.role].responsibility,
            "Required response identity: " + json.dumps(identity),
            "Response JSON schema: " + json.dumps(AgentFindings.model_json_schema()),
            f"<{label}>",
            data,
            f"</{label}>",
            "END UNTRUSTED DATA. Return only the response JSON object.",
        ]
    )
