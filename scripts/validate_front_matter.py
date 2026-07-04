from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docx import Document


FORBIDDEN_TEXT = (
    "[Figure inserted]",
    "[Figure requires review]",
    "[Equation preview inserted]",
    "D:\\",
    ".worktrees",
)
REQUIRED_ORDER = (
    "本科毕业设计（论文）任务书",
    "本人声明",
    "摘    要",
    "Abstract",
    "目录",
)


def validate_front_matter(reference_docx: Path, thesis_docx: Path) -> dict[str, object]:
    del reference_docx  # reserved for later geometric comparison against a golden DOCX.
    result: dict[str, object] = {"status": "pass", "blocking_items": [], "notes": []}
    blocking_items: list[str] = result["blocking_items"]  # type: ignore[assignment]
    notes: list[str] = result["notes"]  # type: ignore[assignment]

    if not thesis_docx.exists() or not thesis_docx.is_file():
        blocking_items.append(f"thesis_docx_missing: {thesis_docx}")
        result["status"] = "failed"
        return result

    try:
        document = Document(str(thesis_docx))
        document_xml = _document_xml(thesis_docx)
    except Exception as exc:
        blocking_items.append(f"thesis_docx_unreadable: {exc}")
        result["status"] = "failed"
        return result

    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    all_text = "\n".join([*paragraphs, _xml_text(document_xml)])
    compact = re.sub(r"\s+", "", all_text)

    _require_text(blocking_items, compact, "单位代码")
    _require_text(blocking_items, compact, "学号")
    _require_text(blocking_items, compact, "分类号")
    _require_text(blocking_items, compact, "毕业设计(论文)")
    for marker in ("学院", "专业", "学生姓名", "指导教师"):
        _require_text(blocking_items, compact, marker)

    cover_end = next(
        (index for index, text in enumerate(paragraphs) if "本科毕业设计（论文）任务书" in text),
        min(len(paragraphs), 30),
    )
    cover_paragraphs = paragraphs[:cover_end]
    if any(text == "究" for text in cover_paragraphs):
        blocking_items.append("cover_title_orphan_character: isolated 究 paragraph found.")

    if not _has_vertical_spine(document_xml):
        blocking_items.append("spine_not_vertical: no tbRl vertical text direction found.")
    if any(text in {"书脊", "Book Spine"} for text in paragraphs):
        blocking_items.append("spine_debug_marker_visible: spine marker rendered as normal paragraph.")

    for marker in FORBIDDEN_TEXT:
        if marker in all_text:
            blocking_items.append(f"forbidden_front_matter_text: {marker}")

    _require_order(blocking_items, paragraphs, REQUIRED_ORDER)
    _inspect_abstract_split(blocking_items, paragraphs)
    _inspect_toc_and_page_numbering(blocking_items, document_xml)

    if not blocking_items:
        notes.append("front matter validation passed.")
    result["status"] = "failed" if blocking_items else "pass"
    return result


def _document_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        return package.read("word/document.xml").decode("utf-8", errors="replace")


def _xml_text(document_xml: str) -> str:
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError:
        return ""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    return "\n".join(node.text or "" for node in root.findall(".//w:t", ns))


def _has_vertical_spine(document_xml: str) -> bool:
    return bool(re.search(r"<w:textDirection\b[^>]*w:val=\"tbRl\"", document_xml))


def _require_text(blocking_items: list[str], compact_text: str, marker: str) -> None:
    if re.sub(r"\s+", "", marker) not in compact_text:
        blocking_items.append(f"front_matter_required_text_missing: {marker}")


def _require_order(blocking_items: list[str], paragraphs: list[str], markers: tuple[str, ...]) -> None:
    positions = {
        marker: next((index for index, text in enumerate(paragraphs) if marker in text), -1)
        for marker in markers
    }
    missing = [marker for marker, index in positions.items() if index < 0]
    if missing:
        blocking_items.append(f"front_matter_order_marker_missing: {', '.join(missing)}")
        return
    if any(positions[markers[index]] >= positions[markers[index + 1]] for index in range(len(markers) - 1)):
        blocking_items.append("front_matter_order_invalid: required pages are out of order.")


def _inspect_abstract_split(blocking_items: list[str], paragraphs: list[str]) -> None:
    try:
        cn_index = paragraphs.index("摘    要")
        en_index = paragraphs.index("Abstract")
    except ValueError:
        return
    keyword_index = next(
        (index for index in range(cn_index, en_index) if paragraphs[index].startswith("关键词")),
        en_index,
    )
    cn_text = "\n".join(paragraphs[cn_index : keyword_index + 1])
    en_text = "\n".join(paragraphs[en_index:])
    for marker in ("Research on", "Author:", "Tutor:"):
        if marker in cn_text:
            blocking_items.append(f"cn_abstract_contains_english_front_matter: {marker}")
    for marker in ("Abstract", "Key Words"):
        if marker not in en_text:
            blocking_items.append(f"en_abstract_required_text_missing: {marker}")


def _inspect_toc_and_page_numbering(blocking_items: list[str], document_xml: str) -> None:
    if 'TOC \\o "1-3"' not in document_xml:
        blocking_items.append("toc_field_missing: Word TOC field not found.")
    pg_num_attrs = re.findall(r"<w:pgNumType\b([^>]*)/?>", document_xml)
    has_roman_start = any('w:fmt="upperRoman"' in attrs and 'w:start="1"' in attrs for attrs in pg_num_attrs)
    has_body_start = any(
        'w:start="1"' in attrs and ('w:fmt="decimal"' in attrs or "w:fmt=" not in attrs)
        for attrs in pg_num_attrs
    )
    if not has_roman_start:
        blocking_items.append("roman_front_matter_page_numbering_missing")
    if not has_body_start:
        blocking_items.append("body_page_number_restart_missing")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate BUAA thesis front matter structure.")
    parser.add_argument("reference_docx", type=Path)
    parser.add_argument("thesis_docx", type=Path)
    args = parser.parse_args(argv)
    result = validate_front_matter(args.reference_docx, args.thesis_docx)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
