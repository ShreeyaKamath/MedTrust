"""Repository-owned role definitions; JSON avoids an additional YAML dependency."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from backend.app.core.config import Settings
from backend.app.orchestration.contracts import AgentId, Contract, Role

ROOT = Path(__file__).resolve().parents[3]
DEFINITIONS = ROOT / "openclaw"


class RoleDefinition(Contract):
    schema_version: Literal["1.0"]
    role: Role
    agent_id: AgentId
    responsibility: str = Field(min_length=1, max_length=2000)
    skills: list[str] = Field(max_length=0)
    tools: list[str] = Field(max_length=0)


class AgentRegistry:
    def __init__(self, definitions: list[RoleDefinition]):
        if len(definitions) != 6 or {item.role for item in definitions} != set(Role):
            raise ValueError("Exactly six unique research roles required")
        if len({item.agent_id for item in definitions}) != 6:
            raise ValueError("Duplicate agent IDs")
        self.roles = {item.role: item for item in definitions}

    @classmethod
    def load(cls, settings: Settings | None = None, root: Path = DEFINITIONS):
        definitions = []
        for role in Role:
            definition = RoleDefinition.model_validate_json(
                (root / "agents" / role / "role.json").read_text(encoding="utf-8")
            )
            if definition.role != role:
                raise ValueError("Role directory mismatch")
            if settings is not None:
                definition = RoleDefinition.model_validate(
                    {
                        **definition.model_dump(),
                        "agent_id": getattr(settings, f"openclaw_{role}"),
                    }
                )
            definitions.append(definition)
        return cls(definitions)
