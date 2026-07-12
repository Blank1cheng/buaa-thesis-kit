from __future__ import annotations

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SECT_PR = f"{{{W_NS}}}sectPr"


def extract_last_section_properties(document_xml: bytes) -> bytes:
    """Return the final w:sectPr element from a Word document XML part."""
    root = etree.fromstring(document_xml, etree.XMLParser(remove_blank_text=False, resolve_entities=False))
    section_nodes = root.findall(f".//{SECT_PR}")
    if not section_nodes:
        return b""
    return etree.tostring(section_nodes[-1], encoding="UTF-8")


__all__ = ["extract_last_section_properties"]

