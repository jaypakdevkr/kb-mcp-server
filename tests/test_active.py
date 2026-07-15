from __future__ import annotations

import threading
from pathlib import Path

from hwp_rag_mcp.active import ActiveDatasetManager
from hwp_rag_mcp.config import DatasetSettings
from hwp_rag_mcp.index import IndexManager
from hwp_rag_mcp.models import IndexStatus, SyncReport


def test_active_dataset_switch_persists_and_reuses_each_index(
    monkeypatch, tmp_path: Path, fake_embeddings_factory, text_document_loader
) -> None:
    monkeypatch.delenv("HWP_RAG_DATASET_DIR", raising=False)
    storage = tmp_path / "storage"
    settings = DatasetSettings(tmp_path / "config")
    first = tmp_path / "첫 번째 규정"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "휴가.hwp").write_text("휴가 규정", encoding="utf-8")
    (second / "계약.hwpx").write_text("계약 규정", encoding="utf-8")

    def factory(path: Path) -> IndexManager:
        return IndexManager(
            path,
            storage_root=storage,
            embeddings_factory=fake_embeddings_factory,
            document_loader=text_document_loader,
        )

    active = ActiveDatasetManager(settings=settings, manager_factory=factory)

    first_change = active.set_dataset_directory(str(first))
    assert first_change.state == "changed"
    assert first_change.index_state == "missing"
    assert active.sync().state == "current"

    second_change = active.set_dataset_directory(str(second))
    assert second_change.state == "changed"
    assert active.sync().state == "current"

    back_to_first = active.set_dataset_directory(str(first))
    assert back_to_first.index_state == "current"
    assert active.search("휴가").results[0].file_name == "휴가.hwp"

    reloaded = ActiveDatasetManager(settings=settings, manager_factory=factory)
    assert reloaded.dataset_dir == first.resolve()
    assert reloaded.status().state == "current"


def test_active_dataset_rejects_invalid_and_locked_changes(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    other = tmp_path / "other"
    explicit.mkdir()
    other.mkdir()
    active = ActiveDatasetManager(explicit)

    locked = active.set_dataset_directory(str(other))
    assert locked.state == "dataset_locked"
    assert locked.dataset_dir == str(explicit.resolve())

    mutable = ActiveDatasetManager(settings=DatasetSettings(tmp_path / "config"))
    invalid = mutable.set_dataset_directory("relative/path")
    assert invalid.state == "invalid"
    assert "absolute" in invalid.message


def test_reset_dataset_does_not_delete_existing_indexes(
    monkeypatch, tmp_path: Path, fake_embeddings_factory, text_document_loader
) -> None:
    monkeypatch.delenv("HWP_RAG_DATASET_DIR", raising=False)
    settings = DatasetSettings(tmp_path / "config")
    selected = tmp_path / "selected"
    selected.mkdir()
    (selected / "sample.hwp").write_text("휴가", encoding="utf-8")
    storage = tmp_path / "storage"

    def factory(path: Path) -> IndexManager:
        return IndexManager(
            path,
            storage_root=storage,
            embeddings_factory=fake_embeddings_factory,
            document_loader=text_document_loader,
        )

    active = ActiveDatasetManager(settings=settings, manager_factory=factory)
    active.set_dataset_directory(str(selected))
    active.sync()
    selected_index = factory(selected).index_dir
    assert selected_index.exists()

    reset = active.reset_dataset_directory()

    assert reset.state == "changed"
    assert reset.source == "default"
    assert selected_index.exists()


def test_dataset_change_waits_for_running_sync(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HWP_RAG_DATASET_DIR", raising=False)
    settings = DatasetSettings(tmp_path / "config")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    settings.save_active_dataset(first)
    sync_started = threading.Event()
    release_sync = threading.Event()
    change_finished = threading.Event()

    class BlockingManager:
        def __init__(self, path: Path) -> None:
            self.dataset_dir = path

        def status(self) -> IndexStatus:
            return IndexStatus(
                state="missing",
                dataset_dir=str(self.dataset_dir),
                index_dir=str(tmp_path / "index"),
                message="missing",
            )

        def sync(self, force: bool = False) -> SyncReport:
            sync_started.set()
            assert release_sync.wait(2)
            return SyncReport(
                state="missing", dataset_dir=str(self.dataset_dir), message="finished"
            )

    active = ActiveDatasetManager(
        settings=settings,
        manager_factory=lambda path: BlockingManager(path),  # type: ignore[arg-type]
    )
    sync_thread = threading.Thread(target=active.sync)
    sync_thread.start()
    assert sync_started.wait(1)

    def change() -> None:
        active.set_dataset_directory(str(second))
        change_finished.set()

    change_thread = threading.Thread(target=change)
    change_thread.start()
    assert not change_finished.wait(0.1)

    release_sync.set()
    sync_thread.join(timeout=2)
    change_thread.join(timeout=2)
    assert change_finished.is_set()
    assert active.dataset_dir == second.resolve()
