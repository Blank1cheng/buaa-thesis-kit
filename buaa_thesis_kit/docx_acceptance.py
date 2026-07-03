from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from docx import Document

from buaa_thesis_kit.models import Metadata


SPINE_MARKERS = ("Book Spine", "书脊")
PDF_PLACEHOLDER_HEADING = "PDF Extracted Text"
EMU_PER_INCH = 914400
PAGE_SCREENSHOT_MIN_WIDTH_IN = 5.0
PAGE_SCREENSHOT_MIN_HEIGHT_IN = 7.4


@dataclass
class DocxOutputInspection:
    blocking_items: list[str] = field(default_factory=list)
    manual_review: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def inspect_docx_output(
    docx_path: Path,
    metadata: Metadata,
    *,
    source_kind: str,
    require_spine: bool,
) -> DocxOutputInspection:
    """Check hard acceptance gates for an authoritative, editable Word output."""
    result = DocxOutputInspection()
    path = Path(docx_path)
    if not path.exists() or not path.is_file():
        result.blocking_items.append(f"word_output_missing: {path}")
        return result

    try:
        package_info = _inspect_docx_package(path)
        document = Document(str(path))
    except Exception as exc:
        result.blocking_items.append(f"word_output_unreadable: {exc}")
        return result

    visible_text = _document_visible_text(document)
    compact_text = _compact_text(visible_text)
    editable_chars = len(compact_text)

    if require_spine and not _contains_any(visible_text, SPINE_MARKERS):
        result.blocking_items.append("spine_missing: authoritative Word output has no book spine marker.")

    _inspect_required_editable_text(
        result,
        compact_text,
        metadata,
        package_info,
        source_kind=source_kind,
    )

    if source_kind.lower() == "pdf" and package_info["page_screenshot_drawing_count"]:
        result.blocking_items.append(
            "word_page_screenshot: PDF-derived Word output contains "
            f"{package_info['page_screenshot_drawing_count']} page-sized drawing(s); "
            "keep page renders only as OCR evidence and rebuild Word content as editable text/tables/equations."
        )

    if PDF_PLACEHOLDER_HEADING in visible_text:
        result.blocking_items.append(
            "pdf_placeholder_heading_visible: remove internal PDF Extracted Text heading from Word output."
        )

    if "[Equation preview inserted]" in visible_text:
        result.blocking_items.append(
            "editable_equation_missing: equation preview image was inserted instead of an editable Word/OMML/OLE equation object."
        )

    if "__BUAA_EDITABLE_EQUATION_OBJECT__" in visible_text:
        result.blocking_items.append(
            "editable_equation_object_token_visible: internal editable equation placeholder was not converted to a Word/OLE object."
        )

    unresolved = re.findall(r"\{\{\s*[A-Z_]+\s*\}\}", visible_text)
    if unresolved:
        result.blocking_items.append(
            f"unresolved_word_placeholders: {', '.join(sorted(set(unresolved)))}"
        )

    if not result.blocking_items:
        result.notes.append(
            f"editable Word validation passed: {editable_chars} editable characters, "
            f"{package_info['drawing_count']} drawings."
        )
    return result


def _inspect_required_editable_text(
    result: DocxOutputInspection,
    compact_text: str,
    metadata: Metadata,
    package_info: dict[str, int],
    *,
    source_kind: str,
) -> None:
    source_label = source_kind.upper() if source_kind else "SOURCE"
    required_values = [
        value
        for value in [
            metadata.title_cn or metadata.title_en,
            metadata.student_id,
        ]
        if _compact_text(value)
    ]
    missing_values = [
        value for value in required_values if _compact_text(value) not in compact_text
    ]
    if missing_values:
        result.blocking_items.append(
            f"editable_text_missing: {source_label}-derived Word output does not expose required "
            f"metadata as editable text: {', '.join(missing_values)}"
        )

    if package_info["drawing_count"] > 0 and len(compact_text) < 30:
        result.blocking_items.append(
            f"editable_text_missing: {source_label}-derived Word output appears image-only."
        )


def _inspect_docx_package(path: Path) -> dict[str, int]:
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        document_xml = package.read("word/document.xml").decode("utf-8", errors="replace")
    drawing_sizes = _drawing_sizes(document_xml)
    return {
        "media_count": sum(1 for name in names if name.startswith("word/media/")),
        "drawing_count": document_xml.count("<w:drawing"),
        "page_screenshot_drawing_count": sum(
            1 for width, height in drawing_sizes if _looks_like_page_screenshot(width, height)
        ),
    }


def _drawing_sizes(document_xml: str) -> list[tuple[float, float]]:
    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    }
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError:
        return []

    sizes: list[tuple[float, float]] = []
    for drawing in root.findall(".//w:drawing", namespaces):
        extent = drawing.find(".//wp:extent", namespaces)
        if extent is None:
            continue
        try:
            width = int(extent.attrib.get("cx", "0")) / EMU_PER_INCH
            height = int(extent.attrib.get("cy", "0")) / EMU_PER_INCH
        except ValueError:
            continue
        sizes.append((width, height))
    return sizes


def _looks_like_page_screenshot(width_in: float, height_in: float) -> bool:
    long_edge = max(width_in, height_in)
    short_edge = min(width_in, height_in)
    return long_edge >= PAGE_SCREENSHOT_MIN_HEIGHT_IN and short_edge >= PAGE_SCREENSHOT_MIN_WIDTH_IN


def _document_visible_text(document) -> str:
    parts: list[str] = []
    parts.extend(paragraph.text for paragraph in document.paragraphs)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.extend(paragraph.text for paragraph in cell.paragraphs)
    return "\n".join(part for part in parts if part is not None)


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


__all__ = ["DocxOutputInspection", "inspect_docx_output"]
