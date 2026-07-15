"""Configuration and path resolution for the local RAG service."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from platformdirs import user_config_path, user_data_path

DEFAULT_MODEL_NAME = "intfloat/multilingual-e5-small"
DEFAULT_CHUNK_SIZE = 1_000
DEFAULT_CHUNK_OVERLAP = 150
DATASET_ENV_VAR = "HWP_RAG_DATASET_DIR"
STORAGE_ENV_VAR = "HWP_RAG_STORAGE_DIR"
SETTINGS_SCHEMA_VERSION = 1

DatasetSource = Literal["cli", "environment", "saved", "default"]


class DatasetSettingsError(RuntimeError):
    """Raised when a persisted dataset setting cannot be read or written safely."""


@dataclass(frozen=True)
class DatasetResolution:
    """Resolved active dataset path and whether MCP is allowed to change it."""

    path: Path
    source: DatasetSource
    mutable: bool
    warning: str | None = None


def normalize_path(value: str | Path) -> Path:
    """Expand and resolve a user-provided path without requiring it to exist."""

    return Path(value).expanduser().resolve(strict=False)


class DatasetSettings:
    """Persist and resolve the active dataset without storing document contents."""

    def __init__(self, config_root: str | Path | None = None) -> None:
        self.config_root = normalize_path(
            config_root or user_config_path("hwp-rag-mcp", appauthor=False)
        )
        self.path = self.config_root / "settings.json"

    def resolve(self, value: str | Path | None = None) -> DatasetResolution:
        """Resolve CLI, environment, saved setting, then the Desktop default."""

        if value is not None:
            return DatasetResolution(normalize_path(value), "cli", False)
        environment_value = os.getenv(DATASET_ENV_VAR)
        if environment_value:
            return DatasetResolution(normalize_path(environment_value), "environment", False)
        try:
            saved = self.load_active_dataset()
        except DatasetSettingsError as exc:
            return DatasetResolution(
                normalize_path(Path.home() / "Desktop" / "dataset"),
                "default",
                True,
                warning=str(exc),
            )
        if saved is not None:
            return DatasetResolution(saved, "saved", True)
        return DatasetResolution(
            normalize_path(Path.home() / "Desktop" / "dataset"), "default", True
        )

    def load_active_dataset(self) -> Path | None:
        """Load the saved active directory from validated JSON."""

        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DatasetSettingsError(f"Saved dataset settings are invalid: {exc}") from exc
        if not isinstance(payload, dict):
            raise DatasetSettingsError("Saved dataset settings must be a JSON object")
        if payload.get("schema_version") != SETTINGS_SCHEMA_VERSION:
            raise DatasetSettingsError("Saved dataset settings use an unsupported schema")
        raw_path = payload.get("active_dataset_dir")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise DatasetSettingsError("Saved dataset settings do not contain a valid path")
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise DatasetSettingsError("Saved dataset path must be absolute")
        return candidate.resolve(strict=False)

    def validate_change_target(self, value: str | Path) -> Path:
        """Validate a user-requested MCP path change without creating directories."""

        raw = str(value).strip()
        if not raw:
            raise ValueError("dataset path must not be empty")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            raise ValueError("dataset path must be absolute or start with '~'")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise ValueError(f"dataset directory does not exist: {candidate}") from exc
        if not resolved.is_dir():
            raise ValueError(f"dataset path is not a directory: {resolved}")
        if not os.access(resolved, os.R_OK):
            raise ValueError(f"dataset directory is not readable: {resolved}")
        return resolved

    def save_active_dataset(self, value: str | Path) -> Path:
        """Atomically persist one validated active dataset directory."""

        resolved = self.validate_change_target(value)
        temporary = self.config_root / f".settings-{uuid.uuid4().hex}.tmp"
        payload = {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "active_dataset_dir": str(resolved),
        }
        try:
            self.config_root.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            with suppress(OSError):
                temporary.chmod(0o600)
            os.replace(temporary, self.path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise DatasetSettingsError(f"Could not save dataset settings: {exc}") from exc
        return resolved

    def reset_active_dataset(self) -> None:
        """Remove the saved preference without touching any dataset or index."""

        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise DatasetSettingsError(f"Could not reset dataset settings: {exc}") from exc


def resolve_dataset_dir(value: str | Path | None = None) -> Path:
    """Resolve dataset path using CLI, environment, saved setting, then Desktop."""

    return DatasetSettings().resolve(value).path


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
