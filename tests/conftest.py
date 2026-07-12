from __future__ import annotations

import math
from pathlib import Path

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


class FakeEmbeddings(Embeddings):
    """Small normalized embedding space for deterministic retrieval tests."""

    terms = ("사과", "바나나", "계약", "휴가")

    @classmethod
    def _vector(cls, text: str) -> list[float]:
        values = [float(text.count(term)) for term in cls.terms]
        if not any(values):
            values = [0.25, 0.25, 0.25, 0.25]
        magnitude = math.sqrt(sum(value * value for value in values))
        return [value / magnitude for value in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@pytest.fixture
def fake_embeddings_factory():
    return FakeEmbeddings


@pytest.fixture
def text_document_loader():
    def load(path: Path) -> list[Document]:
        return [
            Document(
                page_content=path.read_text(encoding="utf-8"),
                metadata={"element_type": "body", "element_index": 0},
            )
        ]

    return load

