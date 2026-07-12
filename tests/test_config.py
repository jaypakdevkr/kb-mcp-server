from __future__ import annotations

from pathlib import Path

import pytest

from hwp_rag_mcp.config import IndexConfig, resolve_dataset_dir


def test_dataset_path_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment_path = tmp_path / "environment"
    cli_path = tmp_path / "cli"
    monkeypatch.setenv("HWP_RAG_DATASET_DIR", str(environment_path))

    assert resolve_dataset_dir() == environment_path.resolve()
    assert resolve_dataset_dir(cli_path) == cli_path.resolve()


def test_index_config_rejects_invalid_overlap(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        IndexConfig(
            dataset_dir=tmp_path / "dataset",
            storage_root=tmp_path / "storage",
            chunk_size=100,
            chunk_overlap=100,
        )

