from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.pdf_export import export_pdf_from_docx
from buaa_thesis_kit.word_convert import convert_doc_to_docx


DEFAULT_OUTPUT = ROOT / "templates" / "official" / "buaa_undergraduate_template.docx"
REQUIRED_DOCX_PARTS = ("[Content_Types].xml", "_rels/.rels", "word/document.xml")


def prepare_official_template(
    source_path: Path,
    output_path: Path = DEFAULT_OUTPUT,
    render_check_dir: Path | None = None,
) -> dict[str, Any]:
    """Convert or copy the official BUAA template into the canonical DOCX slot."""
    source = Path(source_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "status": "failed",
        "source": str(source),
        "output": str(output),
        "conversion_method": None,
        "conversion_message": "",
        "preserved_parts": {},
    }

    if not source.exists() or not source.is_file():
        result["conversion_message"] = f"source missing: {source}"
        _write_manifest(output.parent, result)
        return result

    suffix = source.suffix.lower()
    if suffix == ".docx":
        if not _is_valid_docx(source):
            result["conversion_method"] = "copy_docx"
            result["conversion_message"] = "source is not a valid DOCX package"
            _write_manifest(output.parent, result)
            return result
        if source.resolve() != output.resolve():
            shutil.copy2(source, output)
        result["conversion_method"] = "copy_docx"
        result["conversion_message"] = "official DOCX copied"
    elif suffix == ".doc":
        ok, message = convert_doc_to_docx(source, output)
        result["conversion_method"] = "word_convert"
        result["conversion_message"] = message
        if not ok or not _is_valid_docx(output):
            _write_manifest(output.parent, result)
            return result
    else:
        result["conversion_message"] = f"unsupported official template extension: {source.suffix}"
        _write_manifest(output.parent, result)
        return result

    result["preserved_parts"] = _inspect_docx_parts(output)
    result["status"] = "pass" if _is_valid_docx(output) else "failed"
    if render_check_dir is not None and result["status"] == "pass":
        result["render_check"] = _render_check(output, Path(render_check_dir))
    _write_manifest(output.parent, result)
    return result


def _inspect_docx_parts(path: Path) -> dict[str, bool]:
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        document_xml = package.read("word/document.xml").decode("utf-8", errors="ignore")
    return {
        "styles": "word/styles.xml" in names,
        "numbering": "word/numbering.xml" in names,
        "relationships": "word/_rels/document.xml.rels" in names,
        "media": any(name.startswith("word/media/") for name in names),
        "header_footer": any(name.startswith("word/header") for name in names)
        or any(name.startswith("word/footer") for name in names),
        "sections": "<w:sectPr" in document_xml,
        "fields": "<w:fldSimple" in document_xml or "<w:instrText" in document_xml or "<w:fldChar" in document_xml,
        "textboxes": "txbxContent" in document_xml or "<v:textbox" in document_xml,
    }


def _render_check(docx_path: Path, render_check_dir: Path) -> dict[str, Any]:
    render_check_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = render_check_dir / "official_template.pdf"
    ok, message = export_pdf_from_docx(docx_path, pdf_path)
    check: dict[str, Any] = {"status": "pass" if ok else "needs_review", "message": message, "pdf": str(pdf_path)}
    if not ok:
        return check

    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        check["status"] = "needs_review"
        check["message"] = f"{message}; PyMuPDF unavailable for PNG render: {exc}"
        return check

    page_paths: list[str] = []
    with fitz.open(str(pdf_path)) as document:
        for page_index in range(min(5, document.page_count)):
            pixmap = document.load_page(page_index).get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            page_path = render_check_dir / f"page_{page_index + 1:03d}.png"
            pixmap.save(str(page_path))
            page_paths.append(str(page_path))
    check["pages"] = page_paths
    return check


def _is_valid_docx(path: Path) -> bool:
    try:
        if not path.is_file() or not zipfile.is_zipfile(path):
            return False
        with zipfile.ZipFile(path) as package:
            names = set(package.namelist())
        return all(part in names for part in REQUIRED_DOCX_PARTS)
    except (OSError, zipfile.BadZipFile):
        return False


def _write_manifest(directory: Path, result: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the official BUAA Word template as DOCX.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--render-check-dir", type=Path)
    args = parser.parse_args(argv)

    result = prepare_official_template(args.source, args.out, args.render_check_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

