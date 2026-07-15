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
            "get_dataset_directory",
            "set_dataset_directory",
            "reset_dataset_directory",
            "sync_index",
            "list_documents",
            "search_documents",
        }
        result = await session.call_tool("get_index_status", {})
        assert not result.isError
        sync_result = await session.call_tool("sync_index", {"force": False})
        assert not sync_result.isError
        locked_result = await session.call_tool(
            "set_dataset_directory", {"path": str(tmp_path)}
        )
        assert not locked_result.isError


@pytest.mark.asyncio
async def test_stdio_server_persists_user_requested_dataset_change(tmp_path: Path) -> None:
    home = tmp_path / "home"
    selected = tmp_path / "사용할 문서"
    home.mkdir()
    selected.mkdir()
    source_root = Path(__file__).parents[1] / "src"
    environment = dict(os.environ)
    environment.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "PYTHONPATH": str(source_root),
        }
    )
    environment.pop("HWP_RAG_DATASET_DIR", None)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "hwp_rag_mcp", "serve"],
        env=environment,
    )

    async with (
        stdio_client(parameters) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        changed = await session.call_tool(
            "set_dataset_directory", {"path": str(selected)}
        )
        assert not changed.isError
        assert changed.structuredContent is not None
        assert changed.structuredContent["state"] == "changed"

        configuration = await session.call_tool("get_dataset_directory", {})
        assert not configuration.isError
        assert configuration.structuredContent is not None
        assert configuration.structuredContent["dataset_dir"] == str(selected.resolve())
        assert configuration.structuredContent["source"] == "saved"
