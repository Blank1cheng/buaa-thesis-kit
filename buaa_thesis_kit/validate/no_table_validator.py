from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


@dataclass
class NoTableValidationResult:
    status: str
    blocking_items: list[str] = field(default_factory=list)
    table_locations: list[str] = field(default_factory=list)


def validate_no_tables_after_cover(docx_path: Path) -> NoTableValidationResult:
    """Allow cover tables, but reject any Word table after the first section break."""
    path = Path(docx_path)
    blocking_items: list[str] = []
    locations: list[str] = []

    if not path.exists() or not path.is_file():
        return NoTableValidationResult(
            status="failed",
            blocking_items=[f"docx_missing: {path}"],
        )

    try:
        with zipfile.ZipFile(path) as package:
            names = package.namelist()
            document_xml = package.read("word/document.xml")
            header_footer_parts = [
                name
                for name in names
                if re.match(r"word/(?:header|footer)\d*\.xml$", name)
            ]
            part_payloads = {
                name: package.read(name)
                for name in header_footer_parts
            }
    except Exception as exc:
        return NoTableValidationResult(
            status="failed",
            blocking_items=[f"docx_unreadable: {exc}"],
        )

    locations.extend(_document_table_locations_after_cover(document_xml))
    for part_name, payload in part_payloads.items():
        count = _table_count(payload)
        locations.extend(f"{part_name}:w:tbl[{index}]" for index in range(1, count + 1))

    if locations:
        blocking_items.append(
            "non_cover_tables_forbidden: "
            + ", ".join(locations[:10])
            + (" ..." if len(locations) > 10 else "")
        )

    return NoTableValidationResult(
        status="failed" if blocking_items else "pass",
        blocking_items=blocking_items,
        table_locations=locations,
    )


def _document_table_locations_after_cover(document_xml: bytes) -> list[str]:
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError:
        return ["word/document.xml:unparseable"]
    body = root.find("w:body", NS)
    if body is None:
        return ["word/document.xml:body_missing"]

    locations: list[str] = []
    after_cover = False
    table_index = 0
    for child_index, child in enumerate(list(body), start=1):
        if child.tag == _w("tbl"):
            table_index += 1
            if after_cover:
                locations.append(
                    f"word/document.xml:body_child[{child_index}]:w:tbl[{table_index}]"
                )
        if _contains_section_break(child):
            after_cover = True
    return locations


def _contains_section_break(element: ET.Element) -> bool:
    if element.tag == _w("sectPr"):
        return True
    return element.find(".//w:sectPr", NS) is not None


def _table_count(xml_payload: bytes) -> int:
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError:
        return 1 if b"<w:tbl" in xml_payload else 0
    return len(root.findall(".//w:tbl", NS))


def _w(local_name: str) -> str:
    return f"{{{W_NS}}}{local_name}"


__all__ = ["NoTableValidationResult", "validate_no_tables_after_cover"]
