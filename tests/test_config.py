from __future__ import annotations

from pathlib import Path

import pytest

from hwp_rag_mcp.config import DatasetSettings, IndexConfig, resolve_dataset_dir


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


def test_dataset_settings_precedence_and_persistence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = DatasetSettings(tmp_path / "config")
    saved = tmp_path / "저장된 폴더"
    environment = tmp_path / "environment"
    cli = tmp_path / "cli"
    for path in (saved, environment, cli):
        path.mkdir()

    assert settings.save_active_dataset(saved) == saved.resolve()
    saved_resolution = settings.resolve()
    assert saved_resolution.path == saved.resolve()
    assert saved_resolution.source == "saved"
    assert saved_resolution.mutable

    monkeypatch.setenv("HWP_RAG_DATASET_DIR", str(environment))
    environment_resolution = settings.resolve()
    assert environment_resolution.path == environment.resolve()
    assert environment_resolution.source == "environment"
    assert not environment_resolution.mutable

    cli_resolution = settings.resolve(cli)
    assert cli_resolution.path == cli.resolve()
    assert cli_resolution.source == "cli"
    assert not cli_resolution.mutable


def test_corrupt_saved_settings_fall_back_safely(tmp_path: Path) -> None:
    settings = DatasetSettings(tmp_path / "config")
    settings.config_root.mkdir()
    settings.path.write_text("not json", encoding="utf-8")

    resolution = settings.resolve()

    assert resolution.source == "default"
    assert resolution.mutable
    assert resolution.warning is not None


def test_dataset_change_target_must_be_existing_absolute_directory(tmp_path: Path) -> None:
    settings = DatasetSettings(tmp_path / "config")
    file_path = tmp_path / "document.hwp"
    file_path.write_text("content", encoding="utf-8")

    with pytest.raises(ValueError, match="absolute"):
        settings.validate_change_target("relative/path")
    with pytest.raises(ValueError, match="does not exist"):
        settings.validate_change_target(tmp_path / "missing")
    with pytest.raises(ValueError, match="not a directory"):
        settings.validate_change_target(file_path)
