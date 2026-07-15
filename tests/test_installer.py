from __future__ import annotations

import subprocess
from pathlib import Path

from hwp_rag_mcp.config import DatasetSettings
from hwp_rag_mcp.index import IndexManager
from hwp_rag_mcp.installer import run_setup


def _success(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _finder(tmp_path: Path):
    executables = {
        "uvx": tmp_path / "bin" / "uvx",
        "codex": tmp_path / "bin" / "codex",
        "claude": tmp_path / "bin" / "claude",
    }
    for path in executables.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return lambda name: str(executables[name]) if name in executables else None


def test_setup_dry_run_has_no_side_effects(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    settings = DatasetSettings(tmp_path / "settings")
    dataset = tmp_path / "new dataset"
    calls: list[list[str]] = []

    report = run_setup(
        "codex",
        dataset_dir=dataset,
        dry_run=True,
        settings=settings,
        runner=lambda command: calls.append(command) or _success(command),
        finder=_finder(tmp_path),
    )

    assert report.ok
    assert report.registration == "dry_run"
    assert not report.dataset_created
    assert not dataset.exists()
    assert not settings.path.exists()
    assert calls == []
    assert report.registration_command[-2:] == ["hwp-rag-mcp", "serve"]
    assert "hwp-rag-mcp==0.2.0" in report.registration_command


def test_setup_registers_claude_at_user_scope(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    calls: list[list[str]] = []

    report = run_setup(
        "claude",
        no_sync=True,
        settings=DatasetSettings(tmp_path / "settings"),
        runner=lambda command: calls.append(command) or _success(command),
        finder=_finder(tmp_path),
    )

    assert report.ok
    assert report.registration == "added"
    assert report.dataset_created
    assert calls[0][1:9] == [
        "mcp",
        "add",
        "--transport",
        "stdio",
        "--scope",
        "user",
        "hwp-rag",
        "--",
    ]


def test_setup_detects_identical_codex_configuration(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    finder = _finder(tmp_path)
    uvx = str((tmp_path / "bin" / "uvx").resolve())
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        "\n".join(
            [
                "[mcp_servers.hwp-rag]",
                f'command = "{uvx}"',
                "args = [\"--python\", \"3.12\", \"--from\", "
                "\"hwp-rag-mcp==0.2.0\", \"hwp-rag-mcp\", \"serve\"]",
            ]
        ),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    report = run_setup(
        "codex",
        no_sync=True,
        settings=DatasetSettings(tmp_path / "settings"),
        runner=lambda command: calls.append(command) or _success(command),
        finder=finder,
    )

    assert report.ok
    assert report.registration == "unchanged"
    assert calls == []


def test_setup_conflict_requires_approval_and_failed_replace_restores_config(
    monkeypatch, tmp_path: Path
) -> None:
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    codex_home.mkdir()
    config = codex_home / "config.toml"
    original = b'[mcp_servers.hwp-rag]\ncommand = "other"\nargs = []\n'
    config.write_bytes(original)
    finder = _finder(tmp_path)
    calls: list[list[str]] = []

    conflict = run_setup(
        "codex",
        no_sync=True,
        settings=DatasetSettings(tmp_path / "settings"),
        runner=lambda command: calls.append(command) or _success(command),
        finder=finder,
    )
    assert not conflict.ok
    assert conflict.registration == "conflict"
    assert calls == []

    def fail_add(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "remove" in command:
            config.write_text("", encoding="utf-8")
            return _success(command)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="add failed")

    replaced = run_setup(
        "codex",
        no_sync=True,
        replace_existing=True,
        settings=DatasetSettings(tmp_path / "settings"),
        runner=fail_add,
        finder=finder,
    )

    assert not replaced.ok
    assert replaced.registration == "failed"
    assert config.read_bytes() == original


def test_setup_saves_custom_dataset_and_builds_first_index(
    monkeypatch,
    tmp_path: Path,
    fake_embeddings_factory,
    text_document_loader,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    dataset = tmp_path / "회사 규정"
    dataset.mkdir()
    (dataset / "휴가.hwp").write_text("휴가 규정", encoding="utf-8")
    settings = DatasetSettings(tmp_path / "settings")

    def manager_factory(path: Path) -> IndexManager:
        return IndexManager(
            path,
            storage_root=tmp_path / "storage",
            embeddings_factory=fake_embeddings_factory,
            document_loader=text_document_loader,
        )

    report = run_setup(
        "codex",
        dataset_dir=dataset,
        settings=settings,
        runner=_success,
        finder=_finder(tmp_path),
        manager_factory=manager_factory,
    )

    assert report.ok
    assert report.sync_performed
    assert report.index_state == "current"
    assert settings.load_active_dataset() == dataset.resolve()


def test_setup_reports_missing_uvx(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))

    report = run_setup(
        "codex",
        no_sync=True,
        settings=DatasetSettings(tmp_path / "settings"),
        finder=lambda name: "/bin/codex" if name == "codex" else None,
    )

    assert not report.ok
    assert report.registration == "failed"
    assert "uvx" in report.message


def test_failed_new_registration_removes_partial_config(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    config = codex_home / "config.toml"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    def fail_after_partial_write(command: list[str]) -> subprocess.CompletedProcess[str]:
        codex_home.mkdir(parents=True, exist_ok=True)
        config.write_text("partial", encoding="utf-8")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")

    report = run_setup(
        "codex",
        dataset_dir=tmp_path / "dataset",
        no_sync=True,
        settings=DatasetSettings(tmp_path / "settings"),
        runner=fail_after_partial_write,
        finder=_finder(tmp_path),
    )

    assert not report.ok
    assert not config.exists()


def test_claude_custom_config_directory_is_respected(monkeypatch, tmp_path: Path) -> None:
    custom_config = tmp_path / "claude-profile"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(custom_config))
    finder = _finder(tmp_path)
    uvx = str((tmp_path / "bin" / "uvx").resolve())
    custom_config.mkdir()
    (custom_config / ".claude.json").write_text(
        "{\n"
        '  "mcpServers": {\n'
        '    "hwp-rag": {\n'
        '      "type": "stdio",\n'
        f'      "command": "{uvx}",\n'
        '      "args": ["--python", "3.12", "--from", '
        '"hwp-rag-mcp==0.2.0", "hwp-rag-mcp", "serve"]\n'
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    report = run_setup(
        "claude",
        dataset_dir=tmp_path / "dataset",
        no_sync=True,
        settings=DatasetSettings(tmp_path / "settings"),
        runner=lambda command: calls.append(command) or _success(command),
        finder=finder,
    )

    assert report.ok
    assert report.registration == "unchanged"
    assert calls == []
