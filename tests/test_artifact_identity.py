import json
from pathlib import Path

from docx import Document


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def test_artifact_identity_detects_report_for_modified_candidate(tmp_path):
    from buaa_thesis_kit.harness.artifact_identity import (
        attach_artifact_identity,
        validate_report_artifact_identity,
    )

    candidate = tmp_path / "thesis.docx"
    _write_docx(candidate, ["clean body"])
    report = attach_artifact_identity({"status": "pass", "failures": []}, candidate_path=candidate)

    candidate.write_bytes(candidate.read_bytes() + b"changed")

    identity_report = validate_report_artifact_identity(report, candidate_path=candidate)

    assert identity_report["status"] == "failed"
    assert identity_report["failures"] == [{"id": "artifact_identity_mismatch"}]


def test_validate_output_text_report_contains_candidate_identity(tmp_path):
    from buaa_thesis_kit.harness.validators import validate_output_text_file

    candidate = tmp_path / "thesis.docx"
    _write_docx(candidate, ["1 绪论", "正文"])

    report = validate_output_text_file(candidate, tmp_path / "output_text_report.json")

    assert report["candidate_path"] == str(candidate)
    assert report["candidate_sha256"]
    assert report["candidate_size"] == candidate.stat().st_size
    written = json.loads((tmp_path / "output_text_report.json").read_text(encoding="utf-8"))
    assert written["candidate_sha256"] == report["candidate_sha256"]


def test_run_harness_direct_candidate_writes_artifact_identity_and_reaches_output_text(tmp_path):
    import scripts.run_harness as harness_script

    candidate = Path("tests/fixtures/bad_outputs/thesis6.docx")

    report = harness_script.run_harness(
        candidate=candidate,
        out_dir=tmp_path / "harness_thesis7",
        sample_mode="truncated",
    )

    assert report["status"] == "failed"
    assert report["failed_stage"] == "output_text"
    status = json.loads((tmp_path / "harness_thesis7" / "status.json").read_text(encoding="utf-8"))
    output_text = json.loads((tmp_path / "harness_thesis7" / "output_text_report.json").read_text(encoding="utf-8"))
    artifact_identity = json.loads((tmp_path / "harness_thesis7" / "artifact_identity.json").read_text(encoding="utf-8"))
    assert status["candidate_sha256"] == output_text["candidate_sha256"]
    assert artifact_identity["candidate_sha256"] == output_text["candidate_sha256"]


def test_pipeline_summary_contains_final_thesis_artifact_identity(tmp_path, monkeypatch):
    import buaa_thesis_kit.pipeline as pipeline
    from buaa_thesis_kit.harness.artifact_identity import sha256_file

    def stub_pdf_export(_source: Path, target: Path) -> tuple[bool, str]:
        target.write_bytes(b"%PDF-1.4\n%%EOF")
        return True, "stubbed pdf export"

    output = tmp_path / "pipeline_gate"
    monkeypatch.setattr(pipeline, "export_pdf_from_docx", stub_pdf_export)

    report = pipeline.run_pipeline(
        Path("tests/fixtures/truncated_input.docx"),
        output,
        sample_mode="truncated",
    )

    thesis_docx = output / "thesis.docx"
    assert report["artifact_identity"]["candidate_path"] == str(thesis_docx)
    assert report["artifact_identity"]["candidate_sha256"] == sha256_file(thesis_docx)
