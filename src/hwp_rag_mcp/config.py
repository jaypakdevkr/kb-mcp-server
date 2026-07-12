"""Configuration and path resolution for the local RAG service."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path

DEFAULT_MODEL_NAME = "intfloat/multilingual-e5-small"
DEFAULT_CHUNK_SIZE = 1_000
DEFAULT_CHUNK_OVERLAP = 150
DATASET_ENV_VAR = "HWP_RAG_DATASET_DIR"
STORAGE_ENV_VAR = "HWP_RAG_STORAGE_DIR"


def normalize_path(value: str | Path) -> Path:
    """Expand and resolve a user-provided path without requiring it to exist."""

    return Path(value).expanduser().resolve(strict=False)


def resolve_dataset_dir(value: str | Path | None = None) -> Path:
    """Resolve dataset path using CLI value, environment, then Desktop default."""

    if value is not None:
        return normalize_path(value)
    environment_value = os.getenv(DATASET_ENV_VAR)
    if environment_value:
        return normalize_path(environment_value)
    return normalize_path(Path.home() / "Desktop" / "dataset")


def resolve_storage_root(value: str | Path | None = None) -> Path:
    """Resolve the private application data directory used for indexes."""

    if value is not None:
        return normalize_path(value)
    environment_value = os.getenv(STORAGE_ENV_VAR)
    if environment_value:
        return normalize_path(environment_value)
    return normalize_path(user_data_path("hwp-rag-mcp", appauthor=False))


def dataset_storage_key(dataset_dir: Path) -> str:
    """Create a stable, non-sensitive storage key for an absolute dataset path."""

    digest = hashlib.sha256(str(dataset_dir).encode("utf-8")).hexdigest()[:16]
    return f"dataset-{digest}"


@dataclass(frozen=True)
class IndexConfig:
    """Immutable settings that affect the generated vector index."""

    dataset_dir: Path
    storage_root: Path
    model_name: str = DEFAULT_MODEL_NAME
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    @property
    def index_dir(self) -> Path:
        return self.storage_root / dataset_storage_key(self.dataset_dir)

