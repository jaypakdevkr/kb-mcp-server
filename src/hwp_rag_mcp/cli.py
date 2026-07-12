"""Command-line interface for status, synchronization, and MCP serving."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .index import IndexManager


def _add_dataset_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="HWP/HWPX folder (CLI > HWP_RAG_DATASET_DIR > ~/Desktop/dataset)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hwp-rag-mcp",
        description="Build and serve a local HWP/HWPX FAISS retrieval index.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Check index freshness")
    _add_dataset_argument(status_parser)

    sync_parser = subparsers.add_parser("sync", help="Explicitly rebuild the index")
    _add_dataset_argument(sync_parser)
    sync_parser.add_argument("--force", action="store_true", help="Rebuild a current index")

    serve_parser = subparsers.add_parser("serve", help="Run the MCP STDIO server")
    _add_dataset_argument(serve_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        from .server import run_server

        run_server(args.dataset_dir)
        return 0

    try:
        manager = IndexManager(args.dataset_dir)
        if args.command == "status":
            print(manager.status().model_dump_json(indent=2))
            return 0
        if args.command == "sync":
            report = manager.sync(force=args.force)
            print(report.model_dump_json(indent=2))
            return 0 if report.state == "current" else 1
    except Exception as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    parser.error(f"Unsupported command: {args.command}")
    return 2

