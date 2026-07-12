"""FastMCP STDIO server exposing the local retrieval index."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from .index import IndexManager
from .models import DocumentSummary, IndexStatus, SearchResponse, SyncReport

SERVER_INSTRUCTIONS = """
Use this server to retrieve evidence from the user's local HWP/HWPX dataset.
Call get_index_status before relying on search. If the index is missing or stale,
ask for permission when appropriate and call sync_index. Use search_documents for
evidence, cite file_name/source in the answer, and never claim facts absent from the
returned chunks. The server retrieves evidence only; the MCP host writes the answer.
""".strip()


def configure_logging() -> None:
    """Keep protocol stdout clean by sending application logs to stderr."""

    root = logging.getLogger("hwp_rag_mcp")
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False


def create_server(
    dataset_dir: str | Path | None = None,
    *,
    manager: IndexManager | None = None,
) -> FastMCP:
    """Create a configured MCP server; dependency injection keeps protocol tests light."""

    configure_logging()
    index_manager = manager or IndexManager(dataset_dir)
    mcp = FastMCP(name="HWP RAG", instructions=SERVER_INSTRUCTIONS, json_response=True)

    @mcp.tool()
    def get_index_status() -> IndexStatus:
        """Check whether the local HWP/HWPX index is missing, current, or stale."""

        return index_manager.status()

    @mcp.tool()
    async def sync_index(
        ctx: Context[ServerSession, None, Any], force: bool = False
    ) -> SyncReport:
        """Explicitly rebuild the local index after files are added, changed, or removed."""

        await ctx.info("Starting explicit HWP/HWPX index synchronization")
        report = await asyncio.to_thread(index_manager.sync, force)
        await ctx.info(report.message)
        return report

    @mcp.tool()
    def list_documents() -> list[DocumentSummary]:
        """List documents represented by the last valid persisted index."""

        return index_manager.list_documents()

    @mcp.tool()
    def search_documents(
        query: str,
        top_k: int = 5,
        file_names: list[str] | None = None,
    ) -> SearchResponse:
        """Retrieve ranked evidence chunks, optionally limited to exact file names."""

        return index_manager.search(query=query, top_k=top_k, file_names=file_names)

    return mcp


def run_server(dataset_dir: str | Path | None = None) -> None:
    """Run the local MCP server over STDIO."""

    create_server(dataset_dir).run(transport="stdio")
