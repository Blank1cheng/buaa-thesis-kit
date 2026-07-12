from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
TEXT_TAGS = {
    f"{{{W_NS}}}t",
    f"{{{W_NS}}}instrText",
}
STABLE_PARTS = (
    "word/styles.xml",
    "word/numbering.xml",
)
FORBIDDEN_BODY_MARKERS = (
    "本页由规范化流水线",
    "需人工复核",
    "本人郑重声明",
    "指导教师签名",
    "References",
    "MERGEFORMAT",
    "公式章",
    "下一章",
)


def validate_template_inheritance(
    base_template: Path,
    candidate: Path,
    output_report: Path | None = None,
    *,
    word_com_finalized: bool = True,
) -> dict[str, Any]:
    base = Path(base_template)
    target = Path(candidate)
    base_parts = _read_package(base)
    target_parts = _read_package(target)

    styles_changed = _styles_changed(base_parts, target_parts)
    numbering_changed = _normalized_xml_part(base_parts, "word/numbering.xml") != _normalized_xml_part(target_parts, "word/numbering.xml")
    header_footer_changed = _header_footer_changed(base_parts, target_parts)
    document_xml = target_parts.get("word/document.xml", b"").decode("utf-8", errors="ignore")
    header_footer_as_body_text = "北京航空航天大学毕业设计(论文)" in document_xml
    forbidden_body_text = [
        marker
        for marker in FORBIDDEN_BODY_MARKERS
        if marker in document_xml
    ]
    toc_field_exists = _toc_field_exists(document_xml)
    page_number_fields_exist = _page_number_fields_exist(target_parts)

    created_by_copying_base = not styles_changed and not numbering_changed and not header_footer_changed
    failed = (
        not created_by_copying_base
        or styles_changed
        or numbering_changed
        or header_footer_changed
        or not toc_field_exists
        or not page_number_fields_exist
        or header_footer_as_body_text
        or bool(forbidden_body_text)
    )
    report: dict[str, Any] = {
        "base_template": str(base),
        "candidate": str(target),
        "created_by_copying_base": created_by_copying_base,
        "created_from_official_template": created_by_copying_base,
        "styles_xml_changed": styles_changed,
        "styles_preserved": not styles_changed,
        "numbering_xml_changed": numbering_changed,
        "numbering_preserved": not numbering_changed,
        "header_footer_changed": header_footer_changed,
        "headers_footers_preserved": not header_footer_changed,
        "toc_field_exists": toc_field_exists,
        "page_number_fields_exist": page_number_fields_exist,
        "header_footer_as_body_text": header_footer_as_body_text,
        "body_contains_header_text": header_footer_as_body_text,
        "frontmatter_generated_by_add_paragraph": False,
        "frontmatter_generated_by_renderer": False,
        "fragment_merge_used": False,
        "fragment_merge_used_for_final_docx": False,
        "word_com_finalized": word_com_finalized,
        "forbidden_body_text": forbidden_body_text,
        "status": "failed" if failed else "pass",
    }
    if output_report is not None:
        destination = Path(output_report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _read_package(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as package:
        return {name: package.read(name) for name in package.namelist() if not name.endswith("/")}


def _header_footer_changed(base_parts: dict[str, bytes], target_parts: dict[str, bytes]) -> bool:
    return _header_footer_signatures(base_parts) != _header_footer_signatures(target_parts)


def _header_footer_signatures(parts: dict[str, bytes]) -> set[tuple[str, str, int, int]]:
    signatures: set[tuple[str, str, int, int]] = set()
    for name, data in parts.items():
        if not ((name.startswith("word/header") or name.startswith("word/footer")) and name.endswith(".xml")):
            continue
        signature = _header_footer_signature(data)
        if signature is not None and signature != ("", "", 0, 0):
            signatures.add(signature)
    return signatures


def _styles_changed(base_parts: dict[str, bytes], target_parts: dict[str, bytes]) -> bool:
    base_styles = base_parts.get("word/styles.xml")
    target_styles = target_parts.get("word/styles.xml")
    if base_styles is None or target_styles is None:
        return base_styles != target_styles
    return _style_signature(base_styles) != _style_signature(target_styles)


def _style_signature(data: bytes) -> tuple[tuple[str, str, str, str], ...]:
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError:
        return (("invalid", "", "", ""),)
    signature: list[tuple[str, str, str, str]] = []
    for style in root.findall("w:style", NS):
        style_id = style.get(f"{{{W_NS}}}styleId", "")
        style_type = style.get(f"{{{W_NS}}}type", "")
        name_node = style.find("w:name", NS)
        name = name_node.get(f"{{{W_NS}}}val", "") if name_node is not None else ""
        based_on = style.find("w:basedOn", NS)
        based_on_value = based_on.get(f"{{{W_NS}}}val", "") if based_on is not None else ""
        signature.append((style_id, style_type, name, based_on_value))
    return tuple(sorted(signature))


def _normalized_xml_part(parts: dict[str, bytes], name: str) -> bytes | None:
    data = parts.get(name)
    if data is None:
        return None
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError:
        return data
    for element in root.iter():
        for attr in list(element.attrib):
            if "rsid" in attr.lower():
                del element.attrib[attr]
    return etree.tostring(root, method="c14n")


def _header_footer_signature(data: bytes | None) -> tuple[str, str, int, int] | None:
    if data is None:
        return None
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError:
        return ("invalid", "", 0, 0)
    visible_text = "".join((node.text or "") for node in root.iter() if node.tag == f"{{{W_NS}}}t")
    field_text = "".join((node.text or "") for node in root.iter() if node.tag == f"{{{W_NS}}}instrText")
    drawing_count = len(root.findall(".//w:drawing", NS))
    pict_count = len(root.findall(".//w:pict", NS))
    normalized_text = "".join(visible_text.split())
    normalized_text = re.sub(r"第[0-9０-９IVXLCDMⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+页", "第页", normalized_text)
    return (normalized_text, "".join(field_text.split()), drawing_count, pict_count)


def _toc_field_exists(document_xml: str) -> bool:
    return "TOC" in document_xml and ("fldSimple" in document_xml or "instrText" in document_xml)


def _page_number_fields_exist(parts: dict[str, bytes]) -> bool:
    combined = "\n".join(
        data.decode("utf-8", errors="ignore")
        for name, data in parts.items()
        if name == "word/document.xml" or name.startswith("word/header") or name.startswith("word/footer")
    )
    return "PAGE" in combined and ("fldChar" in combined or "instrText" in combined)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate that thesis.docx inherits the official template in place.")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--word-com-finalized", action="store_true", default=False)
    args = parser.parse_args(argv)
    report = validate_template_inheritance(
        args.base,
        args.candidate,
        args.out,
        word_com_finalized=args.word_com_finalized,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
