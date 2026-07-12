from __future__ import annotations

import json
from pathlib import Path

from buaa_thesis_kit.extract.harness import validate_extraction_model


def _good_model() -> dict:
    return {
        "degree_type": "undergraduate",
        "metadata": {
            "title_cn": "基于实拍图像的光电系统性能评估关键技术研究",
            "student_name": "崔润昊",
            "advisor": "唐荫韬",
            "college": "自动化科学与电气工程学院",
            "major": "自动化",
            "date": "2021 年 5 月",
            "unit_code": "10006",
            "student_id": "17375303",
            "classification": "TP273",
            "evidence": {
                field: {
                    "file": "source.docx",
                    "method": "metadata-test",
                    "paragraph_index": index,
                    "page_hint": 1,
                    "confidence": 0.92,
                    "requires_review": False,
                }
                for index, field in enumerate(
                    [
                        "title_cn",
                        "student_name",
                        "advisor",
                        "college",
                        "major",
                        "date",
                        "unit_code",
                        "student_id",
                        "classification",
                    ]
                )
            },
        },
        "abstract_cn": {"body": "本文研究光电系统性能评估方法。", "keywords": ["光电系统", "性能评估"]},
        "abstract_en": {"body": "This thesis studies evaluation.", "keywords": ["evaluation"]},
        "body": [
            {
                "type": "chapter",
                "number": "1",
                "title": "绪论",
                "source_trace": {
                    "source_file": "source.docx",
                    "source_type": "docx",
                    "chunk_id": "body",
                    "paragraph_start": 13,
                    "paragraph_end": 13,
                    "block_index": 0,
                    "confidence": 0.86,
                },
            }
        ],
        "references": [],
    }


def test_good_model_writes_extraction_reports(tmp_path: Path):
    out = tmp_path / "harness"

    result = validate_extraction_model(
        _good_model(),
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=out,
        sample_mode="truncated",
    )

    assert result["status"] in {"pass", "needs_review"}
    assert result["gate_board"]["E02"]["status"] == "pass"
    assert (out / "extraction_gate_board.json").exists()
    assert (out / "extraction_failure_queue.json").exists()
    assert (out / "source_identity_report.json").exists()
    assert (out / "metadata_report.json").exists()
    source = Path("tests/fixtures/truncated_input.docx").resolve()
    source_identity = json.loads(
        (out / "source_identity_report.json").read_text(encoding="utf-8")
    )
    assert source_identity["source_path"] == str(source)
    assert source_identity["size"] == source.stat().st_size
    assert len(source_identity["sha256"]) == 64
    metadata = json.loads((out / "metadata_report.json").read_text(encoding="utf-8"))
    assert metadata["resolved"]["student_name"]["value"] == "崔润昊"


def test_missing_required_metadata_fails_with_stable_failure_id(tmp_path: Path):
    model = _good_model()
    model["metadata"]["student_name"] = ""
    model["metadata"]["evidence"].pop("student_name")

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["status"] == "failed"
    assert result["gate_board"]["E02"]["status"] == "failed"
    assert any(item["id"].startswith("H-E02") for item in result["failure_queue"])
    assert any(item["field"] == "student_name" for item in result["failure_queue"])


def test_low_confidence_metadata_is_needs_review_not_pass(tmp_path: Path):
    model = _good_model()
    model["metadata"]["evidence"]["title_cn"]["confidence"] = 0.55

    result = validate_extraction_model(
        model,
        source_path=Path("tests/fixtures/truncated_input.docx"),
        out_dir=tmp_path / "harness",
        sample_mode="truncated",
    )

    assert result["gate_board"]["E02"]["status"] == "needs_review"
    assert any(item["reason"] == "low_confidence_metadata" for item in result["failure_queue"])
