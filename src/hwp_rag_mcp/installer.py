"""One-command Codex and Claude Code MCP host registration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

from . import __version__
from .config import DatasetSettings, normalize_path
from .models import (
    IndexState,
    RegistrationState,
    SetupClient,
    SetupReport,
    SyncReport,
)

if TYPE_CHECKING:
    from .index import IndexManager

SERVER_NAME = "hwp-rag"
TOOL_PYTHON_VERSION = "3.12"
SUPPORTED_EXTENSIONS = {".hwp", ".hwpx"}

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
ExecutableFinder = Callable[[str], str | None]
SetupManagerFactory = Callable[[Path], "IndexManager"]


class SetupError(RuntimeError):
    """Expected setup failure that should be returned as structured JSON."""


@dataclass(frozen=True)
class _FileSnapshot:
    existed: bool
    content: bytes = b""


@dataclass(frozen=True)
class _RegistrationResult:
    state: RegistrationState
    command: list[str]
    message: str


def _default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _snapshot(path: Path) -> _FileSnapshot:
    try:
        return _FileSnapshot(path.exists(), path.read_bytes() if path.exists() else b"")
    except OSError as exc:
        raise SetupError(f"Could not read existing host configuration: {exc}") from exc


def _restore(path: Path, snapshot: _FileSnapshot) -> None:
    try:
        if not snapshot.existed:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}-{uuid.uuid4().hex}.tmp"
        temporary.write_bytes(snapshot.content)
        os.replace(temporary, path)
    except OSError as exc:
        raise SetupError(f"Could not restore the previous host configuration: {exc}") from exc


def _codex_config_path() -> Path:
    root = os.getenv("CODEX_HOME")
    return normalize_path(root or Path.home() / ".codex") / "config.toml"


def _claude_config_path() -> Path:
    custom_root = os.getenv("CLAUDE_CONFIG_DIR")
    if custom_root:
        return normalize_path(custom_root) / ".claude.json"
    return normalize_path(Path.home() / ".claude.json")


def _read_codex_entry(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("rb") as stream:
            payload = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SetupError(f"Codex configuration is invalid: {exc}") from exc
    servers = payload.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise SetupError("Codex mcp_servers configuration must be a table")
    entry = servers.get(SERVER_NAME)
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise SetupError(f"Codex MCP entry {SERVER_NAME!r} must be a table")
    return entry


def _read_claude_entry(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SetupError(f"Claude Code configuration is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise SetupError("Claude Code configuration must be a JSON object")
    servers = payload.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise SetupError("Claude Code mcpServers configuration must be an object")
    entry = servers.get(SERVER_NAME)
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise SetupError(f"Claude Code MCP entry {SERVER_NAME!r} must be an object")
    return entry


def _server_command(uvx: str) -> tuple[str, list[str]]:
    return (
        uvx,
        [
            "--python",
            TOOL_PYTHON_VERSION,
            "--from",
            f"hwp-rag-mcp=={__version__}",
            "hwp-rag-mcp",
            "serve",
        ],
    )


def _same_entry(client: SetupClient, entry: dict[str, Any], uvx: str) -> bool:
    command, args = _server_command(uvx)
    if entry.get("command") != command or entry.get("args", []) != args:
        return False
    if client == "claude" and entry.get("type", "stdio") != "stdio":
        return False
    return not entry.get("env")


def _registration_commands(
    client: SetupClient, client_executable: str, uvx: str
) -> tuple[list[str], list[str]]:
    server_command, server_args = _server_command(uvx)
    if client == "codex":
        add = [
            client_executable,
            "mcp",
            "add",
            SERVER_NAME,
            "--",
            server_command,
            *server_args,
        ]
        remove = [client_executable, "mcp", "remove", SERVER_NAME]
    else:
        add = [
            client_executable,
            "mcp",
            "add",
            "--transport",
            "stdio",
            "--scope",
            "user",
            SERVER_NAME,
            "--",
            server_command,
            *server_args,
        ]
        remove = [
            client_executable,
            "mcp",
            "remove",
            "--scope",
            "user",
            SERVER_NAME,
        ]
    return add, remove


def _command_error(result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "unknown command failure").strip()
    return detail[:2_000]


def _register_host(
    client: SetupClient,
    client_executable: str,
    uvx: str,
    *,
    replace_existing: bool,
    dry_run: bool,
    runner: CommandRunner,
) -> _RegistrationResult:
    config_path = _codex_config_path() if client == "codex" else _claude_config_path()
    entry = (
        _read_codex_entry(config_path)
        if client == "codex"
        else _read_claude_entry(config_path)
    )
    add_command, remove_command = _registration_commands(client, client_executable, uvx)
    if entry is not None and _same_entry(client, entry, uvx):
        return _RegistrationResult(
            "unchanged", add_command, "The matching MCP host configuration already exists."
        )
    if entry is not None and not replace_existing:
        return _RegistrationResult(
            "conflict",
            add_command,
            (
                f"An MCP server named {SERVER_NAME!r} already exists with different settings. "
                "Review it and rerun with --replace-existing only after user approval."
            ),
        )
    if dry_run:
        return _RegistrationResult(
            "dry_run", add_command, "Dry run: the MCP host configuration was not changed."
        )

    snapshot = _snapshot(config_path)
    replacing = entry is not None
    if replacing:
        removed = runner(remove_command)
        if removed.returncode != 0:
            return _RegistrationResult(
                "failed",
                add_command,
                f"Could not remove the conflicting MCP configuration: {_command_error(removed)}",
            )

    added = runner(add_command)
    if added.returncode != 0:
        _restore(config_path, snapshot)
        return _RegistrationResult(
            "failed",
            add_command,
            f"Could not register the MCP server: {_command_error(added)}",
        )
    return _RegistrationResult(
        "replaced" if replacing else "added",
        add_command,
        "The MCP server was registered successfully.",
    )


def _contains_documents(dataset_dir: Path) -> bool:
    try:
        return any(
            path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in SUPPORTED_EXTENSIONS
            for path in dataset_dir.rglob("*")
        )
    except OSError:
        return False


def _failure_report(
    client: SetupClient,
    dataset_dir: Path,
    message: str,
    *,
    registration: RegistrationState = "failed",
    registration_command: list[str] | None = None,
) -> SetupReport:
    state: IndexState = "missing"
    if dataset_dir.is_dir() and _contains_documents(dataset_dir):
        from .index import IndexManager

        state = IndexManager(dataset_dir).status().state
    return SetupReport(
        ok=False,
        client=client,
        dataset_dir=str(dataset_dir),
        registration=registration,
        index_state=state,
        registration_command=registration_command or [],
        message=message,
        next_steps=["Resolve the reported problem and run setup again."],
    )


def run_setup(
    client: SetupClient,
    *,
    dataset_dir: str | Path | None = None,
    no_sync: bool = False,
    replace_existing: bool = False,
    dry_run: bool = False,
    settings: DatasetSettings | None = None,
    runner: CommandRunner | None = None,
    finder: ExecutableFinder | None = None,
    manager_factory: SetupManagerFactory | None = None,
) -> SetupReport:
    """Create the dataset, register one host, and optionally build the first index."""

    dataset_settings = settings or DatasetSettings()
    command_runner = runner or _default_runner
    executable_finder = finder or shutil.which
    resolution = dataset_settings.resolve(dataset_dir)
    selected = resolution.path

    uvx = executable_finder("uvx")
    client_executable = executable_finder(client)
    if uvx is None:
        return _failure_report(
            client,
            selected,
            "uvx was not found. Install uv from https://docs.astral.sh/uv/ and retry.",
        )
    if client_executable is None:
        return _failure_report(
            client,
            selected,
            f"The {client} CLI was not found on PATH.",
        )
    uvx = str(normalize_path(uvx))
    client_executable = str(normalize_path(client_executable))

    dataset_created = False
    if selected.exists() and not selected.is_dir():
        return _failure_report(client, selected, f"Dataset path is not a directory: {selected}")
    if not selected.exists() and not dry_run:
        try:
            selected.mkdir(parents=True, exist_ok=False)
            dataset_created = True
        except OSError as exc:
            return _failure_report(client, selected, f"Could not create dataset directory: {exc}")

    settings_snapshot = _snapshot(dataset_settings.path)
    if dataset_dir is not None and not dry_run:
        try:
            selected = dataset_settings.save_active_dataset(selected)
        except (ValueError, RuntimeError) as exc:
            return _failure_report(client, selected, str(exc))

    try:
        registration = _register_host(
            client,
            client_executable,
            uvx,
            replace_existing=replace_existing,
            dry_run=dry_run,
            runner=command_runner,
        )
    except SetupError as exc:
        if dataset_dir is not None and not dry_run:
            _restore(dataset_settings.path, settings_snapshot)
        return _failure_report(client, selected, str(exc))

    if registration.state in {"conflict", "failed"}:
        if dataset_dir is not None and not dry_run:
            _restore(dataset_settings.path, settings_snapshot)
        return _failure_report(
            client,
            selected,
            registration.message,
            registration=registration.state,
            registration_command=registration.command,
        )

    sync_report: SyncReport | None = None
    sync_performed = False
    has_documents = selected.is_dir() and _contains_documents(selected)
    if has_documents:
        if manager_factory is None:
            from .index import IndexManager

            manager = IndexManager(selected)
        else:
            manager = manager_factory(selected)
    if not dry_run and not no_sync and has_documents:
        sync_report = manager.sync()
        sync_performed = True
        index_state = sync_report.state
    elif has_documents:
        index_state = manager.status().state
    else:
        index_state = "missing"

    ok = sync_report is None or sync_report.state == "current"
    restart_required = registration.state in {"added", "replaced"}
    next_steps: list[str] = []
    if restart_required:
        next_steps.append("Restart the MCP host or start a new session to load hwp-rag.")
    if not has_documents:
        next_steps.append(f"Add .hwp or .hwpx files to {selected}, then call sync_index.")
    elif index_state != "current":
        next_steps.append("Run sync again after resolving the reported indexing failures.")
    else:
        next_steps.append("The selected dataset is indexed and ready for search.")

    return SetupReport(
        ok=ok,
        client=client,
        dataset_dir=str(selected),
        dataset_created=dataset_created,
        registration=registration.state,
        index_state=index_state,
        sync_performed=sync_performed,
        sync_report=sync_report,
        restart_required=restart_required,
        registration_command=registration.command,
        message=registration.message,
        next_steps=next_steps,
    )
