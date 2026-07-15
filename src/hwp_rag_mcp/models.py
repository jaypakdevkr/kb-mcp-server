"""Structured public response models for the CLI and MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IndexState = Literal["missing", "current", "stale"]
DatasetSource = Literal["cli", "environment", "saved", "default"]
DatasetChangeState = Literal["changed", "unchanged", "dataset_locked", "invalid"]
SetupClient = Literal["codex", "claude"]
RegistrationState = Literal[
    "added", "unchanged", "replaced", "conflict", "failed", "dry_run"
]


class IndexStatus(BaseModel):
    """Current relationship between the dataset and persisted index."""

    state: IndexState
    dataset_dir: str
    index_dir: str
    document_count: int = 0
    chunk_count: int = 0
    changed_files: list[str] = Field(default_factory=list)
    message: str


class SyncFailure(BaseModel):
    """One file that could not be indexed."""

    file_name: str
    error: str


class SyncReport(BaseModel):
    """Summary of a complete explicit synchronization run."""

    state: IndexState
    dataset_dir: str
    indexed_files: list[str] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)
    failed_files: list[SyncFailure] = Field(default_factory=list)
    chunk_count: int = 0
    message: str


class DatasetConfiguration(BaseModel):
    """Active dataset selection and whether it can be changed through MCP."""

    dataset_dir: str
    source: DatasetSource
    mutable: bool
    exists: bool
    index_state: IndexState
    message: str


class DatasetChangeReport(BaseModel):
    """Result of selecting or resetting the active dataset directory."""

    state: DatasetChangeState
    previous_dataset_dir: str
    dataset_dir: str
    source: DatasetSource
    mutable: bool
    index_state: IndexState
    candidate_file_count: int = 0
    message: str
    next_steps: list[str] = Field(default_factory=list)


class SetupReport(BaseModel):
    """Machine-readable installation and host registration result."""

    ok: bool
    client: SetupClient
    server_name: str = "hwp-rag"
    dataset_dir: str
    dataset_created: bool = False
    registration: RegistrationState
    index_state: IndexState
    sync_performed: bool = False
    sync_report: SyncReport | None = None
    restart_required: bool = False
    registration_command: list[str] = Field(default_factory=list)
    message: str
    next_steps: list[str] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    """Document represented in the persisted vector index."""

    file_name: str
    source: str
    file_type: str
    chunk_count: int


class SearchResult(BaseModel):
    """One ranked evidence chunk returned to an MCP host."""

    rank: int
    score: float
    text: str
    chunk_id: str
    source: str
    file_name: str
    file_type: str
    element_type: str


class SearchResponse(BaseModel):
    """Structured retrieval response, including index readiness."""

    status: IndexState
    query: str
    results: list[SearchResult] = Field(default_factory=list)
    message: str
    stale_files: list[str] = Field(default_factory=list)
