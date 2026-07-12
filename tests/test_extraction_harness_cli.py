from __future__ import annotations

import json
from pathlib import Path

import scripts.validate_extraction as validate_cli

from tests.test_extraction_harness_metadata import _good_model


def test_validate_extraction_cli_writes_reports(tmp_path: Path):
    model_path = tmp_path / "model.json"
    out = tmp_path / "harness"
    model_path.write_text(json.dumps(_good_model(), ensure_ascii=False), encoding="utf-8")

    exit_code = validate_cli.main(
        [
            str(model_path),
            "--source",
            "tests/fixtures/truncated_input.docx",
            "--sample-mode",
            "truncated",
            "--out",
            str(out),
        ]
    )

    assert exit_code == 0
    assert (out / "extraction_gate_board.json").exists()
    assert (out / "metadata_report.json").exists()
