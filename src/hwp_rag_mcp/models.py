"""Structured public response models for the CLI and MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IndexState = Literal["missing", "current", "stale"]


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

