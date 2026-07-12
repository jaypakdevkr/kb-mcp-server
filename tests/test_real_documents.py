from __future__ import annotations

import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from hwp_rag_mcp.index import IndexManager


def _write_owned_hwpx(path: Path, text: str) -> None:
    """Create the minimal HWPX structure consumed by hwp-hwpx-parser."""

    section = f"""<?xml version="1.0" encoding="UTF-8"?>
<hs:sec
  xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
  xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>
</hs:sec>
"""
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Contents/section0.xml", section)


def test_generated_hwpx_parses_and_searches_end_to_end(
    tmp_path: Path, fake_embeddings_factory
) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    _write_owned_hwpx(dataset / "휴가규정.hwpx", "연차 휴가는 15일이며 계약에 따라 신청합니다.")
    manager = IndexManager(
        dataset,
        storage_root=tmp_path / "storage",
        embeddings_factory=fake_embeddings_factory,
    )

    report = manager.sync()
    response = manager.search("휴가", top_k=1)

    assert report.state == "current"
    assert report.failed_files == []
    assert response.results[0].file_name == "휴가규정.hwpx"
    assert "연차 휴가" in response.results[0].text


@pytest.mark.skipif(
    os.getenv("HWP_RAG_REAL_MODEL") != "1",
    reason="Set HWP_RAG_REAL_MODEL=1 to run the downloaded E5 model",
)
def test_generated_hwpx_with_real_local_model(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    _write_owned_hwpx(dataset / "계약휴가.hwpx", "계약직 근로자의 연차 휴가 신청 절차입니다.")
    manager = IndexManager(dataset, storage_root=tmp_path / "storage")

    report = manager.sync()
    response = manager.search("계약직 휴가는 어떻게 신청하나요?", top_k=1)

    assert report.state == "current"
    assert response.status == "current"
    assert response.results[0].file_name == "계약휴가.hwpx"


@pytest.mark.skipif(
    not os.getenv("HWP_RAG_REAL_HWP_FIXTURE"),
    reason="Set HWP_RAG_REAL_HWP_FIXTURE to an owned .hwp test document",
)
def test_user_supplied_hwp_fixture_parses(
    tmp_path: Path, fake_embeddings_factory
) -> None:
    fixture = Path(os.environ["HWP_RAG_REAL_HWP_FIXTURE"]).expanduser().resolve()
    assert fixture.suffix.lower() == ".hwp"
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    target = dataset / fixture.name
    target.write_bytes(fixture.read_bytes())
    manager = IndexManager(
        dataset,
        storage_root=tmp_path / "storage",
        embeddings_factory=fake_embeddings_factory,
    )

    report = manager.sync()

    assert report.state == "current"
    assert fixture.name in report.indexed_files
