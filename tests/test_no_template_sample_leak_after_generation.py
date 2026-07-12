import json
from pathlib import Path

import pytest


def test_pipeline_truncated_fixture_no_template_instruction_or_sample_leak(tmp_path, monkeypatch):
    import buaa_thesis_kit.pipeline as pipeline

    source = Path("tests/fixtures/truncated_input.docx")
    output = tmp_path / "output"
    monkeypatch.setattr(pipeline, "export_pdf_from_docx", lambda _source, target: (False, "pdf export intentionally skipped"))

    report = pipeline.run_pipeline(source, output, sample_mode="truncated")

    output_text_report = json.loads((output / "harness" / "output_text_report.json").read_text(encoding="utf-8"))
    reason_ids = {item["id"] for item in output_text_report["failures"]}
    assert "template_instructions_or_sample_leak" not in reason_ids
    assert "harness_output_text_failed: template_instructions_or_sample_leak" not in report["blocking_items"]
    if output_text_report["status"] != "pass":
        pytest.fail(f"unexpected output_text failures: {output_text_report['failures']}")
