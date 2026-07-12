from __future__ import annotations

from pathlib import Path

from buaa_thesis_kit.extract.harness import validate_extraction_model
from tests.test_extraction_harness_metadata import _good_model


def test_model_with_mergeformat_fails_forbidden_content_gate(tmp_path: Path):
    model = _good_model()
    model["body"].append(
        {
            "type": "equation_placeholder",
            "source_text": "MERGEFORMAT",
            "needs_review": True,
            "source_trace": {
                "source_file": "source.docx",
                "source_type": "docx",
                "chunk_id": "body",
                "paragraph_start": 15,
                "paragraph_end": 15,
                "block_index": 1,
                "confidence": 0.5,
            },
        }
    )

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E09"]["status"] == "failed"
    assert any(item["reason"] == "forbidden_content" and "MERGEFORMAT" in item["evidence"] for item in result["failure_queue"])


def test_body_equation_placeholder_with_ole_filename_fails_equation_gate(tmp_path: Path):
    model = _good_model()
    model["body"].append(
        {
            "type": "equation_placeholder",
            "source_text": "oleObject4.bin",
            "needs_review": True,
            "source_trace": {
                "source_file": "source.docx",
                "source_type": "docx",
                "chunk_id": "body",
                "paragraph_start": 15,
                "paragraph_end": 15,
                "block_index": 1,
                "confidence": 0.5,
            },
        }
    )

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E06"]["status"] == "failed"
    assert any(item["reason"] == "raw_equation_residue" and "oleObject4.bin" in item["evidence"] for item in result["failure_queue"])
