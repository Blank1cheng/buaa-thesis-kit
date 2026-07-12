from __future__ import annotations

import shutil
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
WORD_TEXT_TAGS = {
    f"{{{W_NS}}}t",
    f"{{{W_NS}}}instrText",
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
    classification = replacements.get("{{CLASSIFICATION}}", "")
    if classification:
        _fix_classification_value_spacing(root, classification)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _replace_placeholder_in_nodes(text_nodes: list[etree._Element], placeholder: str, value: str) -> None:
    while True:
        node_texts = [node.text or "" for node in text_nodes]
        full_text = "".join(node_texts)
        start = full_text.find(placeholder)
        if start == -1:
            return
        end = start + len(placeholder)
        start_index, start_offset = _position_to_node(node_texts, start, prefer_next_at_boundary=True)
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


def _position_to_node(
    texts: list[str],
    absolute_offset: int,
    *,
    prefer_next_at_boundary: bool = False,
) -> tuple[int | None, int | None]:
    if absolute_offset == 0:
        return 0, 0
    cursor = 0
    for index, text in enumerate(texts):
        next_cursor = cursor + len(text)
        if prefer_next_at_boundary and absolute_offset == cursor and text:
            return index, 0
        if cursor <= absolute_offset < next_cursor:
            return index, absolute_offset - cursor
        if prefer_next_at_boundary and absolute_offset == next_cursor:
            cursor = next_cursor
            continue
        if absolute_offset == next_cursor:
            return index, len(text)
        cursor = next_cursor
    if texts and absolute_offset == cursor:
        return len(texts) - 1, len(texts[-1])
    return None, None


def _fix_classification_value_spacing(root: etree._Element, value: str) -> None:
    for paragraph in root.findall(".//w:p", NS):
        text = _element_text(paragraph)
        if "分类号" not in text or value not in text:
            continue
        _replace_paragraph_with_split_classification_runs(paragraph, text, value)


def _replace_paragraph_with_split_classification_runs(paragraph: etree._Element, text: str, value: str) -> None:
    runs = list(paragraph.findall("./w:r", NS))
    if not runs:
        return
    prefix, suffix = text.split(value, 1)
    base_rpr = runs[0].find("w:rPr", NS)
    for run in runs:
        paragraph.remove(run)
    paragraph.append(_run_with_text(prefix, base_rpr, preserve=prefix.endswith(" ")))
    value_rpr = deepcopy(base_rpr) if base_rpr is not None else etree.Element(f"{{{W_NS}}}rPr")
    _force_zero_character_spacing(value_rpr)
    paragraph.append(_run_with_text(value, value_rpr, preserve=False))
    if suffix:
        paragraph.append(_run_with_text(suffix, base_rpr, preserve=suffix.startswith(" ") or suffix.endswith(" ")))


def _run_with_text(text: str, rpr: etree._Element | None, *, preserve: bool) -> etree._Element:
    run = etree.Element(f"{{{W_NS}}}r")
    if rpr is not None:
        run.append(deepcopy(rpr))
    text_node = etree.SubElement(run, f"{{{W_NS}}}t")
    if preserve:
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = text
    return run


def _force_zero_character_spacing(rpr: etree._Element) -> None:
    spacing = rpr.find("w:spacing", NS)
    if spacing is None:
        spacing = etree.SubElement(rpr, f"{{{W_NS}}}spacing")
    spacing.set(f"{{{W_NS}}}val", "0")


def _element_text(element: etree._Element) -> str:
    return "".join((node.text or "") for node in element.iter() if node.tag in WORD_TEXT_TAGS)


__all__ = ["replace_docx_placeholders"]
