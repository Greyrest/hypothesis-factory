from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileRef(StrictModel):
    id: str
    filename: str
    path: str
    media_type: str | None = None
    kind: str = "data"


class ModelSelection(StrictModel):
    provider: Literal["anthropic", "openai", "ollama", "mock"] = "anthropic"
    model: str = "claude-opus-4-8"
    enabled: bool = False
    base_url: str | None = None


class ProjectCreate(StrictModel):
    domain: Literal["mining_flotation", "generic"] = "mining_flotation"
    target_kpi: str = Field(min_length=3, max_length=500)
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    constraints: list[str] = Field(default_factory=list, max_length=50)


class RunRequest(StrictModel):
    use_llm: bool | None = None
    weights: dict[str, float] | None = None


class FeedbackRequest(StrictModel):
    vote: Literal["up", "down"] | None = None
    comment: str | None = Field(default=None, max_length=2000)


class RerankRequest(StrictModel):
    weights: dict[str, float] = Field(default_factory=dict)


class IngestionRequest(StrictModel):
    project_id: str
    domain: str
    files: list[FileRef]


class KnowledgeRequest(StrictModel):
    project_id: str
    domain: str
    files: list[FileRef]
    ingestion: dict[str, Any]


class GenerationRequest(StrictModel):
    project_id: str
    domain: str
    target_kpi: str
    constraints: list[str] = Field(default_factory=list)
    ingestion: dict[str, Any]
    knowledge: dict[str, Any]
    model: ModelSelection = Field(default_factory=ModelSelection)
    weights: dict[str, float] | None = None
    feedback: dict[str, Any] = Field(default_factory=dict)


class GraphRequest(StrictModel):
    project: dict[str, Any]
    ingestion: dict[str, Any]
    hypotheses: list[dict[str, Any]]

