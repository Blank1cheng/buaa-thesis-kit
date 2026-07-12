from __future__ import annotations

from pathlib import Path

from buaa_thesis_kit.extract.harness import validate_extraction_model
from tests.test_extraction_harness_metadata import _good_model


def test_chinese_abstract_with_english_residue_fails(tmp_path: Path):
    model = _good_model()
    model["abstract_cn"]["body"] = "本文研究方法。 Abstract Research on system evaluation."

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E03"]["status"] == "failed"
    assert any(item["gate"] == "E03" and item["reason"] == "cn_abstract_contamination" for item in result["failure_queue"])


def test_missing_english_abstract_is_needs_review_in_truncated_mode(tmp_path: Path):
    model = _good_model()
    model["abstract_en"] = {"body": "", "keywords": []}

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E03"]["status"] == "needs_review"
    assert any(item["reason"] == "missing_abstract_en" for item in result["failure_queue"])
