"""Local HWP/HWPX retrieval over the Model Context Protocol."""

import os
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

# Set this before importing FAISS/LangChain modules, which may transitively import
# Hugging Face tokenizers. Parallel tokenizers are unnecessary for this local STDIO
# process and have caused shutdown crashes on some macOS ARM Python builds.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

try:
    __version__ = version("hwp-rag-mcp")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.2.0"

if TYPE_CHECKING:
    from .index import IndexManager
    from .models import (
        DatasetChangeReport,
        DatasetConfiguration,
        DocumentSummary,
        IndexStatus,
        SearchResponse,
        SearchResult,
        SetupReport,
        SyncFailure,
        SyncReport,
    )

__all__ = [
    "DatasetChangeReport",
    "DatasetConfiguration",
    "DocumentSummary",
    "IndexManager",
    "IndexStatus",
    "SearchResponse",
    "SearchResult",
    "SetupReport",
    "SyncFailure",
    "SyncReport",
    "__version__",
]


def __getattr__(name: str) -> Any:
    """Keep public imports compatible without loading ML dependencies eagerly."""

    if name == "IndexManager":
        from .index import IndexManager

        return IndexManager
    if name in {
        "DatasetChangeReport",
        "DatasetConfiguration",
        "DocumentSummary",
        "IndexStatus",
        "SearchResponse",
        "SearchResult",
        "SetupReport",
        "SyncFailure",
        "SyncReport",
    }:
        from . import models

        return getattr(models, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
