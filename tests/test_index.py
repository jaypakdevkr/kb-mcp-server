from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document

from hwp_rag_mcp.index import IndexManager


def _manager(dataset: Path, storage: Path, embeddings_factory, document_loader, **kwargs):
    return IndexManager(
        dataset,
        storage_root=storage,
        embeddings_factory=embeddings_factory,
        document_loader=document_loader,
        **kwargs,
    )


def test_sync_search_filter_and_stale_detection(
    tmp_path: Path, fake_embeddings_factory, text_document_loader
) -> None:
    dataset = tmp_path / "dataset"
    storage = tmp_path / "storage"
    dataset.mkdir()
    apple = dataset / "사과규정.hwp"
    banana = dataset / "바나나규정.hwpx"
    apple.write_text("사과 사과 계약 안내", encoding="utf-8")
    banana.write_text("바나나 휴가 안내", encoding="utf-8")
    (dataset / "ignored.txt").write_text("사과", encoding="utf-8")
    manager = _manager(
        dataset,
        storage,
        fake_embeddings_factory,
        text_document_loader,
        chunk_size=20,
        chunk_overlap=4,
    )

    assert manager.status().state == "missing"
    report = manager.sync()
    assert report.state == "current"
    assert report.indexed_files == ["바나나규정.hwpx", "사과규정.hwp"]
    assert manager.status().state == "current"
    assert not list(manager.index_dir.glob("*.pkl"))

    response = manager.search("사과", top_k=1)
    assert response.status == "current"
    assert response.results[0].file_name == "사과규정.hwp"
    assert response.results[0].score > 0.8

    filtered = manager.search("사과", top_k=2, file_names=["바나나규정.hwpx"])
    assert [result.file_name for result in filtered.results] == ["바나나규정.hwpx"]

    summaries = manager.list_documents()
    assert {summary.file_name for summary in summaries} == {"사과규정.hwp", "바나나규정.hwpx"}

    apple.write_text("사과 계약 안내 수정", encoding="utf-8")
    stale = manager.status()
    assert stale.state == "stale"
    assert stale.changed_files == ["사과규정.hwp"]
    blocked = manager.search("사과")
    assert blocked.status == "stale"
    assert blocked.results == []
    assert "sync_index" in blocked.message


def test_short_table_is_preserved_while_long_body_is_split(
    tmp_path: Path, fake_embeddings_factory
) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    source = dataset / "sample.hwpx"
    source.write_text("placeholder", encoding="utf-8")

    def loader(_path: Path) -> list[Document]:
        return [
            Document(
                page_content="사과 " * 30,
                metadata={"element_type": "body", "element_index": 0},
            ),
            Document(
                page_content="|항목|내용|\n|---|---|\n|휴가|15일|",
                metadata={"element_type": "table", "element_index": 1},
            ),
        ]

    manager = _manager(
        dataset,
        tmp_path / "storage",
        fake_embeddings_factory,
        loader,
        chunk_size=40,
        chunk_overlap=5,
    )
    assert manager.sync().state == "current"
    payload = json.loads((manager.index_dir / "documents.json").read_text(encoding="utf-8"))
    element_types = [item["metadata"]["element_type"] for item in payload["documents"]]
    assert element_types.count("body") > 1
    assert element_types.count("table") == 1


def test_corrupt_persisted_data_is_stale(
    tmp_path: Path, fake_embeddings_factory, text_document_loader
) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "sample.hwp").write_text("휴가 규정", encoding="utf-8")
    manager = _manager(
        dataset,
        tmp_path / "storage",
        fake_embeddings_factory,
        text_document_loader,
    )
    assert manager.sync().state == "current"

    documents_path = manager.index_dir / "documents.json"
    documents_path.write_text("{}", encoding="utf-8")

    status = manager.status()
    assert status.state == "stale"
    assert "checksum" in status.message


def test_failed_rebuild_preserves_previous_index(
    tmp_path: Path, fake_embeddings_factory, text_document_loader
) -> None:
    dataset = tmp_path / "dataset"
    storage = tmp_path / "storage"
    dataset.mkdir()
    source = dataset / "sample.hwp"
    source.write_text("휴가 규정", encoding="utf-8")
    manager = _manager(
        dataset,
        storage,
        fake_embeddings_factory,
        text_document_loader,
    )
    assert manager.sync().state == "current"
    original_index = (manager.index_dir / "index.faiss").read_bytes()

    source.write_text("휴가 규정 변경", encoding="utf-8")

    def failing_loader(_path: Path) -> list[Document]:
        raise RuntimeError("parse failed")

    failing_manager = _manager(
        dataset,
        storage,
        fake_embeddings_factory,
        failing_loader,
    )
    report = failing_manager.sync()
    assert report.state == "stale"
    assert report.failed_files[0].file_name == "sample.hwp"
    assert (manager.index_dir / "index.faiss").read_bytes() == original_index


def test_symlinked_document_is_not_indexed(
    tmp_path: Path, fake_embeddings_factory, text_document_loader
) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    outside = tmp_path / "outside.hwp"
    outside.write_text("사과 비밀", encoding="utf-8")
    link = dataset / "linked.hwp"
    try:
        link.symlink_to(outside)
    except OSError:
        return

    manager = _manager(
        dataset,
        tmp_path / "storage",
        fake_embeddings_factory,
        text_document_loader,
    )
    assert manager.sync().state == "missing"
