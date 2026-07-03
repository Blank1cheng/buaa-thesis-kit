from pathlib import Path

from pypdf import PdfWriter

import buaa_thesis_kit.pdf_export as pdf_export
from buaa_thesis_kit.pdf_export import _verify_pdf_file, export_pdf_from_docx
from buaa_thesis_kit.validate import build_report, validate_clean_output, write_report_md


def _write_valid_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_required_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "thesis.docx").write_bytes(b"docx")
    _write_valid_pdf(output_dir / "thesis.pdf")
    (output_dir / "thesis.tex").write_text("tex", encoding="utf-8")
    (output_dir / "report.md").write_text("report", encoding="utf-8")
    (output_dir / "image").mkdir()


def test_validate_clean_output_passes_with_minimal_nonempty_files_and_image_dir(tmp_path):
    output_dir = tmp_path / "output"
    _write_required_outputs(output_dir)

    ok, messages = validate_clean_output(output_dir)

    assert ok is True
    assert messages == []


def test_validate_clean_output_rejects_unexpected_process_files_at_top_level(tmp_path):
    output_dir = tmp_path / "output"
    _write_required_outputs(output_dir)
    (output_dir / "debug.json").write_text("{}", encoding="utf-8")
    (output_dir / "cache").mkdir()

    ok, messages = validate_clean_output(output_dir)

    assert ok is False
    assert any("debug.json" in message and "unexpected" in message.lower() for message in messages)
    assert any("cache" in message and "unexpected" in message.lower() for message in messages)


def test_validate_clean_output_rejects_missing_and_empty_required_files(tmp_path):
    output_dir = tmp_path / "output"
    _write_required_outputs(output_dir)
    (output_dir / "thesis.pdf").unlink()
    (output_dir / "thesis.tex").write_text("", encoding="utf-8")

    ok, messages = validate_clean_output(output_dir)

    assert ok is False
    assert any("thesis.pdf" in message and "missing" in message.lower() for message in messages)
    assert any("thesis.tex" in message and "empty" in message.lower() for message in messages)


def test_validate_clean_output_rejects_malformed_pdf(tmp_path):
    output_dir = tmp_path / "output"
    _write_required_outputs(output_dir)
    (output_dir / "thesis.pdf").write_bytes(b"%PDF-1.4\nbody")

    ok, messages = validate_clean_output(output_dir)

    assert ok is False
    assert any("thesis.pdf" in message and "invalid" in message.lower() for message in messages)


def test_validate_clean_output_rejects_image_that_is_not_directory(tmp_path):
    output_dir = tmp_path / "output"
    _write_required_outputs(output_dir)
    (output_dir / "image").rmdir()
    (output_dir / "image").write_text("not a directory", encoding="utf-8")

    ok, messages = validate_clean_output(output_dir)

    assert ok is False
    assert any("image" in message and "directory" in message.lower() for message in messages)


def test_validate_clean_output_rejects_process_files_inside_image_dir(tmp_path):
    output_dir = tmp_path / "output"
    _write_required_outputs(output_dir)
    image_dir = output_dir / "image"
    (image_dir / "figure.png").write_bytes(b"image")
    (image_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (image_dir / "notes.md").write_text("notes", encoding="utf-8")
    (image_dir / "cache").mkdir()

    ok, messages = validate_clean_output(output_dir)

    assert ok is False
    assert any("manifest.json" in message for message in messages)
    assert any("notes.md" in message for message in messages)
    assert any("cache" in message for message in messages)


def test_validate_clean_output_allows_cache_named_media_and_rejects_process_suffixes(tmp_path):
    output_dir = tmp_path / "output"
    _write_required_outputs(output_dir)
    image_dir = output_dir / "image"
    (image_dir / "cache_architecture.png").write_bytes(b"image")
    (image_dir / "debug_frame.mp4").write_bytes(b"media")
    (image_dir / "compile.fls").write_text("process", encoding="utf-8")
    (image_dir / "thesis.synctex.gz").write_text("process", encoding="utf-8")
    (image_dir / "notes.txt").write_text("process", encoding="utf-8")

    ok, messages = validate_clean_output(output_dir)

    assert ok is False
    assert not any("cache_architecture.png" in message for message in messages)
    assert not any("debug_frame.mp4" in message for message in messages)
    assert any("compile.fls" in message for message in messages)
    assert any("thesis.synctex.gz" in message for message in messages)
    assert any("notes.txt" in message for message in messages)


def test_validate_clean_output_rejects_process_dirs_inside_image_dir(tmp_path):
    output_dir = tmp_path / "output"
    _write_required_outputs(output_dir)
    image_dir = output_dir / "image"
    (image_dir / "cache").mkdir()
    (image_dir / "debug").mkdir()
    (image_dir / "__pycache__").mkdir()

    ok, messages = validate_clean_output(output_dir)

    assert ok is False
    assert any("cache" in message for message in messages)
    assert any("debug" in message for message in messages)
    assert any("__pycache__" in message for message in messages)


def test_build_report_marks_failed_for_blocking_items_or_failed_outputs():
    blocked = build_report(
        source="source.docx",
        outputs={"thesis.docx": "pass", "thesis.pdf": "pass"},
        summary={"items": 2},
        blocking_items=["missing metadata"],
        manual_review=[],
        notes=[],
    )
    failed_output = build_report(
        source="source.docx",
        outputs={"thesis.docx": "pass", "thesis.pdf": "failed"},
        summary={"items": 2},
        blocking_items=[],
        manual_review=[],
        notes=[],
    )

    assert blocked["status"] == "failed"
    assert failed_output["status"] == "failed"


def test_build_report_marks_needs_review_for_manual_review_or_output_review():
    manual = build_report(
        source="source.docx",
        outputs={"thesis.docx": "pass", "thesis.pdf": "pass", "thesis.tex": "pass", "image": "pass"},
        summary={"items": 2},
        blocking_items=[],
        manual_review=["check equations"],
        notes=[],
    )
    output_review = build_report(
        source="source.docx",
        outputs={"thesis.docx": "pass", "thesis.pdf": "needs_review", "thesis.tex": "pass", "image": "pass"},
        summary={"items": 2},
        blocking_items=[],
        manual_review=[],
        notes=[],
    )

    assert manual["status"] == "needs_review"
    assert output_review["status"] == "needs_review"


def test_build_report_marks_pass_when_no_failures_or_reviews():
    report = build_report(
        source="source.docx",
        outputs={"thesis.docx": "pass", "thesis.pdf": "pass", "thesis.tex": "pass", "image": "pass"},
        summary={"items": 2},
        blocking_items=[],
        manual_review=[],
        notes=[],
    )

    assert report == {
        "status": "pass",
        "source": "source.docx",
        "outputs": {"thesis.docx": "pass", "thesis.pdf": "pass", "thesis.tex": "pass", "image": "pass"},
        "summary": {"items": 2},
        "blocking_items": [],
        "manual_review": [],
        "notes": [],
    }


def test_build_report_fails_for_missing_required_or_unknown_output_statuses():
    no_outputs = build_report(
        source="source.docx",
        outputs={},
        summary={},
        blocking_items=[],
        manual_review=[],
        notes=[],
    )
    missing_pdf = build_report(
        source="source.docx",
        outputs={"pdf": "missing"},
        summary={},
        blocking_items=[],
        manual_review=[],
        notes=[],
    )
    skipped_tex = build_report(
        source="source.docx",
        outputs={"word": "pass", "pdf": "pass", "tex": "skipped", "image": "pass"},
        summary={},
        blocking_items=[],
        manual_review=[],
        notes=[],
    )

    assert no_outputs["status"] == "failed"
    assert missing_pdf["status"] == "failed"
    assert skipped_tex["status"] == "failed"


def test_write_report_md_includes_policy_text_sections_and_list_items(tmp_path):
    report = build_report(
        source="source.docx",
        outputs={"thesis.docx": "pass", "thesis.pdf": "needs_review"},
        summary={"figures": 1, "tables": 2},
        blocking_items=["missing PDF export"],
        manual_review=["confirm equation layout"],
        notes=["generated from template"],
    )
    path = tmp_path / "report.md"

    write_report_md(report, path)

    text = path.read_text(encoding="utf-8")
    assert "Word is authoritative" in text
    assert "PDF exported from Word" in text
    assert "TeX auxiliary" in text
    for section in ("## Status", "## Outputs", "## Summary", "## Blocking Items", "## Manual Review", "## Notes"):
        assert section in text
    assert "- thesis.pdf: needs_review" in text
    assert "- figures: 1" in text
    assert "- missing PDF export" in text
    assert "- confirm equation layout" in text
    assert "- generated from template" in text


def test_export_pdf_from_docx_returns_false_for_missing_source_without_junk(tmp_path):
    source = tmp_path / "missing.docx"
    pdf_path = tmp_path / "output" / "thesis.pdf"

    ok, reason = export_pdf_from_docx(source, pdf_path)

    assert ok is False
    assert "missing" in reason.lower() or "not found" in reason.lower()
    assert not pdf_path.exists()
    assert not pdf_path.parent.exists()


def test_export_pdf_from_docx_returns_false_for_non_docx_source_without_junk(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("not docx", encoding="utf-8")
    pdf_path = tmp_path / "output" / "thesis.pdf"

    ok, reason = export_pdf_from_docx(source, pdf_path)

    assert ok is False
    assert ".docx" in reason.lower()
    assert not pdf_path.exists()
    assert not pdf_path.parent.exists()


def test_export_pdf_from_docx_returns_true_when_stubbed_word_writes_valid_pdf(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    pdf_path = tmp_path / "output" / "thesis.pdf"

    def fake_word_export(_source: Path, target: Path) -> tuple[bool, str]:
        _write_valid_pdf(target)
        return True, "stubbed Word export"

    def unexpected_libreoffice(_source: Path, _target: Path) -> tuple[bool, str]:
        raise AssertionError("LibreOffice should not run after valid Word export")

    monkeypatch.setattr(pdf_export.os, "name", "nt")
    monkeypatch.setattr(pdf_export, "_export_with_word_com", fake_word_export)
    monkeypatch.setattr(pdf_export, "_export_with_libreoffice", unexpected_libreoffice)

    ok, reason = export_pdf_from_docx(source, pdf_path)

    assert ok is True
    assert "Word" in reason
    assert pdf_path.exists()


def test_export_pdf_from_docx_removes_stubbed_invalid_word_pdf(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    pdf_path = tmp_path / "output" / "thesis.pdf"

    def fake_word_export(_source: Path, target: Path) -> tuple[bool, str]:
        target.write_bytes(b"%PDF-1.4\nbody")
        return True, "stubbed invalid Word export"

    monkeypatch.setattr(pdf_export.os, "name", "nt")
    monkeypatch.setattr(pdf_export, "_export_with_word_com", fake_word_export)
    monkeypatch.setattr(pdf_export, "_export_with_libreoffice", lambda _source, _target: (False, "no LibreOffice"))

    ok, reason = export_pdf_from_docx(source, pdf_path)

    assert ok is False
    assert "invalid PDF" in reason
    assert not pdf_path.exists()


def test_export_pdf_from_docx_returns_true_when_stubbed_libreoffice_writes_valid_pdf(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    pdf_path = tmp_path / "output" / "thesis.pdf"

    def fake_libreoffice(_source: Path, target: Path) -> tuple[bool, str]:
        _write_valid_pdf(target)
        return True, "stubbed LibreOffice export"

    monkeypatch.setattr(pdf_export, "_export_with_word_com", lambda _source, _target: (False, "no Word"))
    monkeypatch.setattr(pdf_export, "_export_with_libreoffice", fake_libreoffice)

    ok, reason = export_pdf_from_docx(source, pdf_path)

    assert ok is True
    assert "LibreOffice" in reason
    assert pdf_path.exists()


def test_export_pdf_from_docx_rejects_existing_target_directory_without_exporting(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    pdf_path = tmp_path / "output" / "thesis.pdf"
    pdf_path.mkdir(parents=True)

    def unexpected_export(_source: Path, _target: Path) -> tuple[bool, str]:
        _write_valid_pdf(pdf_path / "source.pdf")
        return True, "unexpected export"

    monkeypatch.setattr(pdf_export, "_export_with_word_com", unexpected_export)
    monkeypatch.setattr(pdf_export, "_export_with_libreoffice", unexpected_export)

    ok, reason = export_pdf_from_docx(source, pdf_path)

    assert ok is False
    assert "directory" in reason.lower() or "path" in reason.lower()
    assert list(pdf_path.iterdir()) == []


def test_libreoffice_export_returns_false_when_move_fails(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    target = tmp_path / "output" / "thesis.pdf"
    target.parent.mkdir()

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, check, capture_output, text, timeout):
        outdir = Path(command[command.index("--outdir") + 1])
        _write_valid_pdf(outdir / "source.pdf")
        return Result()

    def fake_move(_source: str, _target: str):
        raise OSError("move failed")

    monkeypatch.setattr(pdf_export.shutil, "which", lambda _name: "soffice")
    monkeypatch.setattr(pdf_export.subprocess, "run", fake_run)
    monkeypatch.setattr(pdf_export.shutil, "move", fake_move)

    ok, reason = pdf_export._export_with_libreoffice(source, target)

    assert ok is False
    assert "move failed" in reason


def test_libreoffice_export_rejects_existing_target_directory_without_nested_pdf(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    target = tmp_path / "output" / "thesis.pdf"
    target.mkdir(parents=True)

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, check, capture_output, text, timeout):
        outdir = Path(command[command.index("--outdir") + 1])
        _write_valid_pdf(outdir / "source.pdf")
        return Result()

    monkeypatch.setattr(pdf_export.shutil, "which", lambda _name: "soffice")
    monkeypatch.setattr(pdf_export.subprocess, "run", fake_run)

    ok, reason = pdf_export._export_with_libreoffice(source, target)

    assert ok is False
    assert "directory" in reason.lower() or "path" in reason.lower()
    assert list(target.iterdir()) == []


def test_verify_pdf_file_checks_existence_size_header_and_parseability(tmp_path):
    missing = tmp_path / "missing.pdf"
    empty = tmp_path / "empty.pdf"
    invalid = tmp_path / "invalid.pdf"
    truncated = tmp_path / "truncated.pdf"
    valid = tmp_path / "valid.pdf"
    empty.write_bytes(b"")
    invalid.write_bytes(b"not a pdf")
    truncated.write_bytes(b"%PDF-1.4\nbody")
    _write_valid_pdf(valid)

    missing_ok, missing_reason = _verify_pdf_file(missing)
    empty_ok, empty_reason = _verify_pdf_file(empty)
    invalid_ok, invalid_reason = _verify_pdf_file(invalid)
    truncated_ok, truncated_reason = _verify_pdf_file(truncated)
    valid_ok, valid_reason = _verify_pdf_file(valid)

    assert missing_ok is False
    assert "missing" in missing_reason.lower() or "not found" in missing_reason.lower()
    assert empty_ok is False
    assert "empty" in empty_reason.lower()
    assert invalid_ok is False
    assert "%PDF" in invalid_reason
    assert truncated_ok is False
    assert "invalid" in truncated_reason.lower()
    assert valid_ok is True
    assert valid_reason == "PDF export verified"
