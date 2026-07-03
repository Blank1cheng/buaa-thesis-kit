import base64
import json
from pathlib import Path

import pytest
import fitz
from docx import Document
from pypdf import PdfWriter

from buaa_thesis_kit.validate import validate_clean_output


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _write_valid_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def _stub_pdf_export(_source: Path, target: Path) -> tuple[bool, str]:
    _write_valid_pdf(target)
    return True, "stubbed Word PDF export"


def _failing_pdf_export(_source: Path, _target: Path) -> tuple[bool, str]:
    return False, "Word PDF export unavailable in this environment"


def _stub_doc_conversion(source: Path, target: Path) -> tuple[bool, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(Path(source).read_bytes())
    return True, "stubbed DOC to DOCX conversion"


def _failing_doc_conversion(_source: Path, _target: Path) -> tuple[bool, str]:
    return False, "Word DOC conversion unavailable in this environment"


def _write_source_docx(path: Path, *, with_image: bool = False) -> None:
    document = Document()
    for text in [
        "中文题目：流水线集成测试",
        "英文题目：Pipeline Integration Test",
        "学生姓名：张三",
        "学号：20370001",
        "学院：自动化科学与电气工程学院",
        "专业：自动化",
        "指导教师：李四",
        "日期：2026年6月",
        "摘要",
        "这是中文摘要。",
        "ABSTRACT",
        "This is the English abstract.",
        "1 绪论",
        "正文。",
        "参考文献",
        "[1] 王五. 流水线测试[J]. 2026.",
    ]:
        document.add_paragraph(text)
    if with_image:
        image_path = path.with_suffix(".png")
        image_path.write_bytes(TINY_PNG)
        document.add_picture(str(image_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def _write_text_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: PDF Pipeline Thesis",
                "Student Name: Zhang San",
                "Student ID: 20370001",
                "College: Automation College",
                "Major: Automation",
                "Advisor: Li Si",
                "Date: 2026-07",
                "1 Introduction",
                "This PDF contains extractable thesis text.",
                "References",
                "[1] Wang Wu. Test reference. 2026.",
            ]
        ),
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _public_names(output_dir: Path) -> list[str]:
    return sorted(path.name for path in output_dir.iterdir())


def test_run_pipeline_success_writes_clean_contract_and_removes_work_dir(tmp_path, monkeypatch):
    import buaa_thesis_kit.pipeline as pipeline

    source = tmp_path / "source.docx"
    output = tmp_path / "output"
    _write_source_docx(source, with_image=True)
    output.mkdir()
    (output / "old-debug.json").write_text("{}", encoding="utf-8")
    (output / "image").mkdir()
    (output / "image" / "manifest.json").write_text("old process file", encoding="utf-8")
    monkeypatch.setattr(pipeline, "export_pdf_from_docx", _stub_pdf_export)

    report = pipeline.run_pipeline(source, output)

    assert report["status"] == "needs_review"
    assert _public_names(output) == ["image", "report.md", "thesis.docx", "thesis.pdf", "thesis.tex"]
    ok, messages = validate_clean_output(output)
    assert ok is True
    assert messages == []
    assert not (output / "old-debug.json").exists()
    assert not (output / "image" / "manifest.json").exists()
    assert not list(tmp_path.glob("output_work*"))
    assert any("figure" in item.lower() for item in report["manual_review"])
    assert any("tex" in item.lower() for item in report["manual_review"])
    assert "image/" in (output / "thesis.tex").read_text(encoding="utf-8")


def test_run_pipeline_pdf_failure_reports_blocking_without_process_files(tmp_path, monkeypatch):
    import buaa_thesis_kit.pipeline as pipeline

    source = tmp_path / "source.docx"
    output = tmp_path / "output"
    _write_source_docx(source)
    monkeypatch.setattr(pipeline, "export_pdf_from_docx", _failing_pdf_export)

    report = pipeline.run_pipeline(source, output)

    assert report["status"] == "failed"
    assert _public_names(output) == ["image", "report.md", "thesis.docx", "thesis.tex"]
    assert (output / "thesis.docx").is_file()
    assert (output / "thesis.tex").is_file()
    assert not (output / "thesis.pdf").exists()
    assert any("pdf export" in item.lower() for item in report["blocking_items"])
    assert any("thesis.pdf" in item for item in report["blocking_items"])
    assert not any(path.name.endswith((".json", ".log", ".tmp")) for path in output.rglob("*") if path.is_file())
    report_text = (output / "report.md").read_text(encoding="utf-8")
    assert "Word PDF export unavailable" in report_text
    assert "Missing required output: thesis.pdf" in report_text


def test_run_pipeline_keep_work_retains_adjacent_work_dir_and_keeps_public_output_clean(
    tmp_path, monkeypatch
):
    import buaa_thesis_kit.pipeline as pipeline

    source = tmp_path / "source.docx"
    output = tmp_path / "output"
    _write_source_docx(source, with_image=True)
    monkeypatch.setattr(pipeline, "export_pdf_from_docx", _stub_pdf_export)

    report = pipeline.run_pipeline(source, output, keep_work=True)

    work_dir = output.with_name(output.name + "_work")
    assert report["status"] == "needs_review"
    assert work_dir.is_dir()
    assert (work_dir / "source.docx").is_file()
    assert _public_names(output) == ["image", "report.md", "thesis.docx", "thesis.pdf", "thesis.tex"]
    ok, messages = validate_clean_output(output)
    assert ok is True
    assert messages == []


def test_run_pipeline_text_pdf_input_writes_clean_contract(tmp_path, monkeypatch):
    import buaa_thesis_kit.pipeline as pipeline

    source = tmp_path / "source.pdf"
    output = tmp_path / "output"
    _write_text_pdf(source)
    monkeypatch.setattr(pipeline, "export_pdf_from_docx", _stub_pdf_export)

    report = pipeline.run_pipeline(source, output)

    assert report["status"] == "needs_review"
    assert _public_names(output) == ["image", "report.md", "thesis.docx", "thesis.pdf", "thesis.tex"]
    ok, messages = validate_clean_output(output)
    assert ok is True
    assert messages == []
    assert any("pdf" in item.lower() and "layout" in item.lower() for item in report["manual_review"])
    assert "PDF Pipeline Thesis" in (output / "thesis.tex").read_text(encoding="utf-8")


def test_run_pipeline_doc_input_converts_to_docx_before_extraction(tmp_path, monkeypatch):
    import buaa_thesis_kit.pipeline as pipeline

    docx_source = tmp_path / "source-as-docx.docx"
    source = tmp_path / "source.doc"
    output = tmp_path / "output"
    _write_source_docx(docx_source)
    source.write_bytes(docx_source.read_bytes())
    monkeypatch.setattr(pipeline, "convert_doc_to_docx", _stub_doc_conversion)
    monkeypatch.setattr(pipeline, "export_pdf_from_docx", _stub_pdf_export)

    report = pipeline.run_pipeline(source, output)

    assert report["status"] in {"pass", "needs_review"}
    assert _public_names(output) == ["image", "report.md", "thesis.docx", "thesis.pdf", "thesis.tex"]
    ok, messages = validate_clean_output(output)
    assert ok is True
    assert messages == []
    assert any("doc to docx" in note.lower() for note in report["notes"])


def test_run_pipeline_doc_conversion_failure_writes_failed_report(tmp_path, monkeypatch):
    import buaa_thesis_kit.pipeline as pipeline

    source = tmp_path / "source.doc"
    output = tmp_path / "output"
    source.write_bytes(b"legacy word bytes")
    monkeypatch.setattr(pipeline, "convert_doc_to_docx", _failing_doc_conversion)

    report = pipeline.run_pipeline(source, output)

    assert report["status"] == "failed"
    assert "image" in _public_names(output)
    assert "report.md" in _public_names(output)
    assert any("doc conversion" in item.lower() for item in report["blocking_items"])
    assert "Word DOC conversion unavailable" in (output / "report.md").read_text(encoding="utf-8")


def test_run_pipeline_invalid_pdf_input_writes_failed_report_without_exception(tmp_path):
    import buaa_thesis_kit.pipeline as pipeline

    source = tmp_path / "source.pdf"
    output = tmp_path / "output"
    source.write_bytes(b"%PDF-1.4\nnot a thesis source")

    report = pipeline.run_pipeline(source, output)

    assert report["status"] == "failed"
    assert "image" in _public_names(output)
    assert "report.md" in _public_names(output)
    assert not list(tmp_path.glob("output_work*"))
    assert any("pdf" in item.lower() for item in report["blocking_items"])
    assert "PDF extraction failed" in (output / "report.md").read_text(encoding="utf-8")


def test_run_pipeline_refuses_output_directory_that_contains_source_without_cleanup(tmp_path):
    import buaa_thesis_kit.pipeline as pipeline

    output = tmp_path / "output"
    output.mkdir()
    source = output / "source.docx"
    sentinel = output / "do-not-delete.txt"
    _write_source_docx(source)
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="contains source file"):
        pipeline.run_pipeline(source, output)

    assert source.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_cli_main_prints_json_and_returns_status_based_exit_codes(tmp_path, monkeypatch, capsys):
    import buaa_thesis_kit.pipeline as pipeline
    import scripts.run_pipeline as cli

    source = tmp_path / "source.docx"
    output = tmp_path / "output"
    failed_output = tmp_path / "failed-output"
    failed_source = tmp_path / "source.pdf"
    _write_source_docx(source)
    failed_source.write_bytes(b"%PDF-1.4\nnot a thesis source")
    monkeypatch.setattr(pipeline, "export_pdf_from_docx", _stub_pdf_export)

    pass_code = cli.main([str(source), "--out", str(output)])
    pass_payload = json.loads(capsys.readouterr().out)
    fail_code = cli.main([str(failed_source), "--out", str(failed_output)])
    fail_payload = json.loads(capsys.readouterr().out)

    assert pass_code == 0
    assert pass_payload["status"] in {"pass", "needs_review"}
    assert pass_payload["summary"]["sections"] >= 1
    assert fail_code == 1
    assert fail_payload["status"] == "failed"
