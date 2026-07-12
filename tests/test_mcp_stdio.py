from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_stdio_server_lists_expected_tools(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    source_root = Path(__file__).parents[1] / "src"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(source_root)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "hwp_rag_mcp",
            "serve",
            "--dataset-dir",
            str(dataset),
        ],
        env=environment,
    )

    async with (
        stdio_client(parameters) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {
            "get_index_status",
            "sync_index",
            "list_documents",
            "search_documents",
        }
        result = await session.call_tool("get_index_status", {})
        assert not result.isError
        sync_result = await session.call_tool("sync_index", {"force": False})
        assert not sync_result.isError
