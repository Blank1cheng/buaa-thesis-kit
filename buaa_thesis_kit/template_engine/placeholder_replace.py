from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree


WORD_TEXT_TAGS = {
    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t",
    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}instrText",
}
DEFAULT_PARTS = (
    "word/document.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
)


def replace_docx_placeholders(source: Path, output: Path, values: dict[str, str]) -> None:
    """Replace {{PLACEHOLDER}} text anywhere in a DOCX while preserving run XML.

    The replacement walks Word XML text nodes in document order, so placeholders
    split across adjacent runs, table cells, headers, footers, and text boxes are
    handled without reconstructing paragraphs or losing the first run's style.
    """
    source = Path(source)
    output = Path(output)
    replacements = {f"{{{{{key}}}}}": value for key, value in values.items()}
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="buaa_placeholder_") as temp_dir:
        temp_output = Path(temp_dir) / "output.docx"
        with zipfile.ZipFile(source, "r") as src, zipfile.ZipFile(temp_output, "w", zipfile.ZIP_DEFLATED) as dst:
            names = set(src.namelist())
            replaceable_parts = _replaceable_xml_parts(names)
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename in replaceable_parts:
                    data = _replace_xml_bytes(data, replacements)
                dst.writestr(item, data)
        shutil.move(str(temp_output), str(output))


def _replaceable_xml_parts(names: set[str]) -> set[str]:
    parts = {name for name in DEFAULT_PARTS if name in names}
    parts.update(name for name in names if name.startswith("word/header") and name.endswith(".xml"))
    parts.update(name for name in names if name.startswith("word/footer") and name.endswith(".xml"))
    return parts


def _replace_xml_bytes(data: bytes, replacements: dict[str, str]) -> bytes:
    if b"{{" not in data:
        return data
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = etree.fromstring(data, parser)
    text_nodes = [node for node in root.iter() if node.tag in WORD_TEXT_TAGS]
    for placeholder, value in replacements.items():
        _replace_placeholder_in_nodes(text_nodes, placeholder, value)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _replace_placeholder_in_nodes(text_nodes: list[etree._Element], placeholder: str, value: str) -> None:
    while True:
        node_texts = [node.text or "" for node in text_nodes]
        full_text = "".join(node_texts)
        start = full_text.find(placeholder)
        if start == -1:
            return
        end = start + len(placeholder)
        start_index, start_offset = _position_to_node(node_texts, start)
        end_index, end_offset = _position_to_node(node_texts, end)
        if start_index is None or end_index is None:
            return

        if start_index == end_index:
            original = node_texts[start_index]
            text_nodes[start_index].text = original[:start_offset] + value + original[end_offset:]
            continue

        first_text = node_texts[start_index]
        last_text = node_texts[end_index]
        text_nodes[start_index].text = first_text[:start_offset] + value
        for index in range(start_index + 1, end_index):
            text_nodes[index].text = ""
        text_nodes[end_index].text = last_text[end_offset:]


def _position_to_node(texts: list[str], absolute_offset: int) -> tuple[int | None, int | None]:
    if absolute_offset == 0:
        return 0, 0
    cursor = 0
    for index, text in enumerate(texts):
        next_cursor = cursor + len(text)
        if cursor <= absolute_offset < next_cursor:
            return index, absolute_offset - cursor
        if absolute_offset == next_cursor:
            return index, len(text)
        cursor = next_cursor
    if texts and absolute_offset == cursor:
        return len(texts) - 1, len(texts[-1])
    return None, None


__all__ = ["replace_docx_placeholders"]
