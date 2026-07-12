"""Local HWP/HWPX retrieval over the Model Context Protocol."""

import os
from importlib.metadata import PackageNotFoundError, version

# Set this before importing FAISS/LangChain modules, which may transitively import
# Hugging Face tokenizers. Parallel tokenizers are unnecessary for this local STDIO
# process and have caused shutdown crashes on some macOS ARM Python builds.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

try:
    __version__ = version("hwp-rag-mcp")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.1.1"

from .index import IndexManager
from .models import (
    DocumentSummary,
    IndexStatus,
    SearchResponse,
    SearchResult,
    SyncFailure,
    SyncReport,
)

__all__ = [
    "DocumentSummary",
    "IndexManager",
    "IndexStatus",
    "SearchResponse",
    "SearchResult",
    "SyncFailure",
    "SyncReport",
    "__version__",
]
