from __future__ import annotations

from pathlib import Path

from buaa_thesis_kit.extract.harness import validate_extraction_model
from tests.test_extraction_harness_metadata import _good_model


def test_body_header_footer_residue_fails(tmp_path: Path):
    model = _good_model()
    model["body"].append(
        {
            "type": "paragraph",
            "text": "北京航空航天大学毕业设计(论文)",
            "source_trace": {
                "source_file": "source.docx",
                "source_type": "docx",
                "chunk_id": "body",
                "paragraph_start": 14,
                "paragraph_end": 14,
                "block_index": 1,
                "confidence": 0.7,
            },
        }
    )

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E04"]["status"] == "failed"
    assert any(item["reason"] == "body_forbidden_content" for item in result["failure_queue"])


def test_nonempty_document_without_heading_needs_review(tmp_path: Path):
    model = _good_model()
    model["body"] = [
        {
            "type": "paragraph",
            "text": "本课题来源于国家自然科学基金。",
            "source_trace": {
                "source_file": "source.docx",
                "source_type": "docx",
                "chunk_id": "body",
                "paragraph_start": 14,
                "paragraph_end": 14,
                "block_index": 0,
                "confidence": 0.8,
            },
        }
    ]

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E04"]["status"] == "needs_review"
    assert any(item["reason"] == "missing_body_heading" for item in result["failure_queue"])


def test_section_before_first_chapter_fails_body_structure(tmp_path: Path):
    model = _good_model()
    model["body"] = [
        {
            "type": "section",
            "number": "1.1",
            "title": "课题来源与背景",
            "source_trace": {
                "source_file": "source.docx",
                "source_type": "docx",
                "chunk_id": "body",
                "paragraph_start": 8,
                "paragraph_end": 8,
                "block_index": 0,
                "confidence": 0.86,
            },
        },
        {
            "type": "chapter",
            "number": "1",
            "title": "绪论",
            "source_trace": {
                "source_file": "source.docx",
                "source_type": "docx",
                "chunk_id": "body",
                "paragraph_start": 15,
                "paragraph_end": 15,
                "block_index": 1,
                "confidence": 0.9,
            },
        },
    ]

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E04"]["status"] == "failed"
    assert any(item["reason"] == "body_section_before_chapter" for item in result["failure_queue"])


def test_source_toc_line_in_body_fails_body_structure(tmp_path: Path):
    model = _good_model()
    model["body"].insert(
        0,
        {
            "type": "paragraph",
            "text": "1.1 课题来源与背景 ................................ 1",
            "source_trace": {
                "source_file": "source.docx",
                "source_type": "docx",
                "chunk_id": "body",
                "paragraph_start": 6,
                "paragraph_end": 6,
                "block_index": 0,
                "confidence": 0.8,
            },
        },
    )

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E04"]["status"] == "failed"
    assert any(item["reason"] == "source_toc_leak" for item in result["failure_queue"])
