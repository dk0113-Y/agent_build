from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ExecutorRole = Literal["fast", "pro", "local"]
ReasoningProfile = Literal["none", "low", "medium", "high"]
AutonomyMode = Literal[
    "answer_only",
    "plan_only",
    "read_files",
    "edit_files",
    "execute_commands",
    "external_delegate",
]
RiskLevel = Literal["low", "medium", "high", "critical"]


class MetaDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_goal: str
    task_boundary: str | None
    need_clarification: bool
    clarification_question: str | None
    missing_info: list[str] = Field(default_factory=list)
    need_meta_high: bool
    meta_high_reason: str | None
    executor_role: ExecutorRole
    reasoning_profile: ReasoningProfile
    autonomy_mode: AutonomyMode
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    verifiers: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    need_human_approval: bool
    short_reason: str

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("tools must be empty in V0.4")
        return value

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        allowed = {"project_manager", "general"}
        invalid = sorted(set(value) - allowed)
        if invalid:
            raise ValueError(f"unsupported skills in V0.4: {invalid}")
        return value

    @field_validator("verifiers")
    @classmethod
    def validate_verifiers(cls, value: list[str]) -> list[str]:
        allowed = {"self_check"}
        invalid = sorted(set(value) - allowed)
        if invalid:
            raise ValueError(f"unsupported verifiers in V0.4: {invalid}")
        return value

    def to_metadata(self) -> dict[str, object]:
        return self.model_dump()
