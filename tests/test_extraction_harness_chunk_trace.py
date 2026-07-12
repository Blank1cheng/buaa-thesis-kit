from __future__ import annotations

from pathlib import Path

from buaa_thesis_kit.extract.chunking import parse_ranges
from buaa_thesis_kit.extract.harness import validate_extraction_model
from tests.test_extraction_harness_metadata import _good_model


def test_missing_source_trace_is_needs_review(tmp_path: Path):
    model = _good_model()
    model["body"][0].pop("source_trace")

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E08"]["status"] == "needs_review"
    assert any(item["reason"] == "missing_source_trace" for item in result["failure_queue"])


def test_parse_named_page_ranges():
    ranges = parse_ranges("frontmatter:1-8,body:9-30,references:31-33")

    assert ranges[0].chunk_id == "frontmatter"
    assert ranges[0].page_start == 1
    assert ranges[0].page_end == 8
    assert ranges[2].chunk_id == "references"
    assert ranges[2].page_start == 31
    assert ranges[2].page_end == 33
