from __future__ import annotations

import sys
from types import SimpleNamespace

from hwp_rag_mcp.embeddings import create_local_embeddings


def test_e5_embeddings_use_asymmetric_prompts(monkeypatch) -> None:
    captured = {}
    sentinel = object()

    def fake_hugging_face_embeddings(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setitem(
        sys.modules,
        "langchain_huggingface",
        SimpleNamespace(HuggingFaceEmbeddings=fake_hugging_face_embeddings),
    )

    result = create_local_embeddings()

    assert result is sentinel
    assert captured["model_name"] == "intfloat/multilingual-e5-small"
    assert captured["model_kwargs"] == {"device": "cpu"}
    assert captured["encode_kwargs"] == {
        "normalize_embeddings": True,
        "prompt": "passage: ",
    }
    assert captured["query_encode_kwargs"] == {
        "normalize_embeddings": True,
        "prompt": "query: ",
    }

