"""Thread-safe active dataset selection shared by all MCP tools."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from .config import DatasetResolution, DatasetSettings
from .index import SUPPORTED_EXTENSIONS, IndexManager
from .models import (
    DatasetChangeReport,
    DatasetChangeState,
    DatasetConfiguration,
    DocumentSummary,
    IndexStatus,
    SearchResponse,
    SyncReport,
)

ManagerFactory = Callable[[Path], IndexManager]


def _candidate_file_count(dataset_dir: Path, scan_limit: int = 10_000) -> int:
    """Count supported files with a bounded scan and without following symlinks."""

    if not dataset_dir.is_dir():
        return 0
    count = 0
    scanned = 0
    for root, directories, files in os.walk(dataset_dir, followlinks=False):
        directories[:] = [
            name for name in directories if not (Path(root) / name).is_symlink()
        ]
        count += sum(
            1
            for name in files
            if Path(name).suffix.lower() in SUPPORTED_EXTENSIONS
            and not (Path(root) / name).is_symlink()
        )
        scanned += len(directories) + len(files)
        if scanned >= scan_limit:
            break
    return count


class ActiveDatasetManager:
    """Serialize path changes with index reads and rebuilds."""

    def __init__(
        self,
        dataset_dir: str | Path | None = None,
        *,
        settings: DatasetSettings | None = None,
        manager_factory: ManagerFactory | None = None,
        manager: IndexManager | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._settings = settings or DatasetSettings()
        self._manager_factory = manager_factory or (lambda path: IndexManager(path))
        if manager is not None:
            self._resolution = DatasetResolution(manager.dataset_dir, "cli", False)
            self._manager = manager
        else:
            self._resolution = self._settings.resolve(dataset_dir)
            self._manager = self._manager_factory(self._resolution.path)

    @property
    def dataset_dir(self) -> Path:
        with self._lock:
            return self._manager.dataset_dir

    def get_configuration(self) -> DatasetConfiguration:
        with self._lock:
            status = self._manager.status()
            message = status.message
            if self._resolution.warning:
                message = f"{self._resolution.warning} Falling back safely. {message}"
            return DatasetConfiguration(
                dataset_dir=str(self._manager.dataset_dir),
                source=self._resolution.source,
                mutable=self._resolution.mutable,
                exists=self._manager.dataset_dir.is_dir(),
                index_state=status.state,
                message=message,
            )

    def set_dataset_directory(self, path: str) -> DatasetChangeReport:
        with self._lock:
            previous = self._manager.dataset_dir
            if not self._resolution.mutable:
                return DatasetChangeReport(
                    state="dataset_locked",
                    previous_dataset_dir=str(previous),
                    dataset_dir=str(previous),
                    source=self._resolution.source,
                    mutable=False,
                    index_state=self._manager.status().state,
                    candidate_file_count=_candidate_file_count(previous),
                    message=(
                        "dataset_locked: the server was started with --dataset-dir or "
                        "HWP_RAG_DATASET_DIR. Remove that override and restart before changing "
                        "the active dataset through MCP."
                    ),
                    next_steps=["Remove the dataset override and restart the MCP host."],
                )
            try:
                selected = self._settings.validate_change_target(path)
            except ValueError as exc:
                status = self._manager.status()
                return DatasetChangeReport(
                    state="invalid",
                    previous_dataset_dir=str(previous),
                    dataset_dir=str(previous),
                    source=self._resolution.source,
                    mutable=True,
                    index_state=status.state,
                    candidate_file_count=_candidate_file_count(previous),
                    message=str(exc),
                    next_steps=["Provide an existing readable absolute directory path."],
                )
            if selected == previous:
                status = self._manager.status()
                return DatasetChangeReport(
                    state="unchanged",
                    previous_dataset_dir=str(previous),
                    dataset_dir=str(previous),
                    source=self._resolution.source,
                    mutable=True,
                    index_state=status.state,
                    candidate_file_count=_candidate_file_count(previous),
                    message="The requested directory is already the active dataset.",
                    next_steps=self._index_next_steps(status),
                )

            next_manager = self._manager_factory(selected)
            selected = self._settings.save_active_dataset(selected)
            self._resolution = DatasetResolution(selected, "saved", True)
            self._manager = next_manager
            status = self._manager.status()
            return DatasetChangeReport(
                state="changed",
                previous_dataset_dir=str(previous),
                dataset_dir=str(selected),
                source=self._resolution.source,
                mutable=True,
                index_state=status.state,
                candidate_file_count=_candidate_file_count(selected),
                message="The active dataset directory was changed and saved.",
                next_steps=self._index_next_steps(status),
            )

    def reset_dataset_directory(self) -> DatasetChangeReport:
        with self._lock:
            previous = self._manager.dataset_dir
            if not self._resolution.mutable:
                return DatasetChangeReport(
                    state="dataset_locked",
                    previous_dataset_dir=str(previous),
                    dataset_dir=str(previous),
                    source=self._resolution.source,
                    mutable=False,
                    index_state=self._manager.status().state,
                    candidate_file_count=_candidate_file_count(previous),
                    message=(
                        "dataset_locked: remove the CLI or environment override and restart "
                        "before resetting the active dataset."
                    ),
                    next_steps=["Remove the dataset override and restart the MCP host."],
                )

            self._settings.reset_active_dataset()
            next_resolution = self._settings.resolve()
            next_manager = self._manager_factory(next_resolution.path)
            self._resolution = next_resolution
            self._manager = next_manager
            status = self._manager.status()
            state: DatasetChangeState = (
                "unchanged" if previous == self._manager.dataset_dir else "changed"
            )
            return DatasetChangeReport(
                state=state,
                previous_dataset_dir=str(previous),
                dataset_dir=str(self._manager.dataset_dir),
                source=self._resolution.source,
                mutable=self._resolution.mutable,
                index_state=status.state,
                candidate_file_count=_candidate_file_count(self._manager.dataset_dir),
                message="The saved dataset preference was reset to the Desktop default.",
                next_steps=self._index_next_steps(status),
            )

    @staticmethod
    def _index_next_steps(status: IndexStatus) -> list[str]:
        if status.state == "current":
            return ["The selected dataset is ready for search."]
        return ["Call sync_index before searching the selected dataset."]

    def status(self) -> IndexStatus:
        with self._lock:
            return self._manager.status()

    def sync(self, force: bool = False) -> SyncReport:
        with self._lock:
            return self._manager.sync(force)

    def list_documents(self) -> list[DocumentSummary]:
        with self._lock:
            return self._manager.list_documents()

    def search(
        self,
        query: str,
        top_k: int = 5,
        file_names: list[str] | None = None,
    ) -> SearchResponse:
        with self._lock:
            return self._manager.search(query=query, top_k=top_k, file_names=file_names)
