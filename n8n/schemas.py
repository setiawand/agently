from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


@dataclass
class Deps:
    pass  # workflow_id datang dari argumen tool, tidak perlu deps khusus


class WorkflowIssue(BaseModel):
    workflow_id: str
    workflow_name: str
    status: Literal["healthy", "inactive", "failing", "error"]
    detail: str


class HealthReport(BaseModel):
    summary: str = Field(description="Ringkasan singkat kondisi semua workflow")
    issues: list[WorkflowIssue] = Field(default_factory=list)


class WorkflowProposal(BaseModel):
    """Usulan perubahan dari agent. Agent tidak menulis ke n8n; kode main.py yang menerapkan."""

    workflow_id: str | None = Field(default=None, description="Isi untuk perbaikan; kosong untuk workflow baru")
    name: str | None = Field(default=None, description="Nama workflow (wajib untuk workflow baru)")
    nodes: list[dict[str, Any]]
    connections: dict[str, Any]


class AgentResult(BaseModel):
    task: Literal["health_check", "create_workflow", "fix_workflow"]
    result: str = Field(description="Penjelasan hasil dalam bahasa manusia")
    report: HealthReport | None = None
    proposal: WorkflowProposal | None = None
    action_taken: Literal["none", "applied", "escalated"] = Field(
        default="none", description="Diisi oleh kode, bukan LLM"
    )
    action_detail: str = ""
