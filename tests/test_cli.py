from __future__ import annotations

import json
from pathlib import Path

from hwp_rag_mcp.cli import build_parser, main


def test_status_cli_outputs_structured_json(tmp_path: Path, capsys) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    exit_code = main(["status", "--dataset-dir", str(dataset)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "missing"
    assert payload["dataset_dir"] == str(dataset.resolve())


def test_setup_cli_requires_supported_client() -> None:
    args = build_parser().parse_args(["setup", "--client", "codex", "--dry-run"])

    assert args.command == "setup"
    assert args.client == "codex"
    assert args.dry_run
