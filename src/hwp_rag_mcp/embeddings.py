"""Local multilingual embedding construction."""

from __future__ import annotations

import os

from langchain_core.embeddings import Embeddings

from .config import DEFAULT_MODEL_NAME


def create_local_embeddings(model_name: str = DEFAULT_MODEL_NAME) -> Embeddings:
    """Create the supported local E5 embedder with retrieval prompts enabled."""

    # Hugging Face tokenizers can initialize worker resources that are unnecessary for
    # this single-process STDIO server and unstable in some macOS ARM Python builds.
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True, "prompt": "passage: "},
        query_encode_kwargs={"normalize_embeddings": True, "prompt": "query: "},
    )
