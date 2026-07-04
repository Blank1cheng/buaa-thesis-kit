from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from lxml import etree

from buaa_thesis_kit.models import ContentBlock, ThesisModel
from buaa_thesis_kit.template_engine.placeholder_replace import replace_docx_placeholders


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
TEXT_TAGS = {
    f"{{{W_NS}}}t",
    f"{{{W_NS}}}instrText",
}
BLOCK_PLACEHOLDERS = {
    "ABSTRACT_CN",
    "ABSTRACT_EN",
    "TASK_RAW_MATERIALS",
    "TASK_WORK_CONTENT",
    "TASK_REFERENCES",
    "ACKNOWLEDGEMENT",
    "REFERENCES",
}
FORBIDDEN_BODY_TEXT = (
    "[Figure inserted]",
    "[Figure requires review]",
    "本页由规范化流水线",
    "需人工复核",
    "本人郑重声明",
    "指导教师签名",
    "References",
    "MERGEFORMAT",
    "公式章",
    "下一章",
)


def assemble_in_place(
    instrumented_template: Path,
    model: ThesisModel,
    output_path: Path,
    *,
    style_map_path: Path | None = None,
) -> dict[str, Any]:
    """Copy the instrumented official template and replace content in place."""
    template = Path(instrumented_template)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, output)

    scalar_values = _scalar_placeholders(model)
    replace_docx_placeholders(output, output, scalar_values)

    with tempfile.TemporaryDirectory(prefix="buaa_in_place_") as temp_dir:
        temp_output = Path(temp_dir) / "thesis.docx"
        with zipfile.ZipFile(output, "r") as source:
            document_xml = source.read("word/document.xml")
            updated_document_xml = _replace_document_blocks(
                document_xml,
                model,
                _load_style_map(style_map_path),
            )
            with zipfile.ZipFile(temp_output, "w", zipfile.ZIP_DEFLATED) as target:
                for item in source.infolist():
                    data = updated_document_xml if item.filename == "word/document.xml" else source.read(item.filename)
                    target.writestr(item, data)
        shutil.move(str(temp_output), str(output))

    report = {
        "base_template": str(template),
        "candidate": str(output),
        "created_by_copying_base": True,
        "frontmatter_generated_by_add_paragraph": False,
        "fragment_merge_used": False,
        "status": "pass",
    }
    return report


def _scalar_placeholders(model: ThesisModel) -> dict[str, str]:
    metadata = model.metadata
    title_line1, title_line2 = _split_title(metadata.title_cn)
    front_matter = model.front_matter
    return {
        "UNIT_CODE": metadata.unit_code,
        "STUDENT_ID": metadata.student_id,
        "CLASSIFICATION": metadata.classification,
        "TITLE_CN_LINE1": title_line1,
        "TITLE_CN_LINE2": title_line2,
        "TITLE_CN": metadata.title_cn,
        "COLLEGE": metadata.college,
        "MAJOR": metadata.major,
        "STUDENT_NAME": metadata.student_name,
        "ADVISOR": metadata.advisor,
        "DATE_YEAR_MONTH": metadata.date,
        "SPINE_TITLE_CN": metadata.title_cn,
        "SPINE_STUDENT_NAME": metadata.student_name,
        "SPINE_UNIVERSITY": "北京航空航天大学",
        "TASK_TITLE": metadata.title_cn,
        "TASK_COLLEGE_MAJOR_CLASS": " ".join(part for part in (metadata.college, metadata.major) if part),
        "TASK_STUDENT_NAME": metadata.student_name,
        "TASK_DATE_RANGE": str(front_matter.get("task_date_range", "")),
        "TASK_DEFENSE_DATE": str(front_matter.get("task_defense_date", "")),
        "TASK_GRADE": str(front_matter.get("task_grade", "")),
        "TASK_ADVISOR": metadata.advisor,
        "TASK_DIRECTOR_SIGNATURE": str(front_matter.get("task_director_signature", "")),
        "DECLARATION_STUDENT_NAME": metadata.student_name,
        "DECLARATION_DATE": metadata.date,
        "TITLE_EN": metadata.title_en or str(front_matter.get("title_en", "")),
        "AUTHOR_EN": str(front_matter.get("author_en", "")) or metadata.student_name,
        "TUTOR_EN": str(front_matter.get("tutor_en", "")) or metadata.advisor,
        "KEYWORDS_CN": _front_matter_value(model, "keywords_cn", "chinese_keywords", "cn_keywords", "keywords"),
        "KEYWORDS_EN": _front_matter_value(model, "keywords_en", "english_keywords", "en_keywords"),
    }


def _replace_document_blocks(document_xml: bytes, model: ThesisModel, style_map: dict[str, str]) -> bytes:
    root = etree.fromstring(document_xml, etree.XMLParser(remove_blank_text=False, resolve_entities=False))
    body = root.find("w:body", NS)
    if body is None:
        raise ValueError("Invalid DOCX template: missing word/body")
    _replace_body_range(body, model, style_map)
    _replace_block_placeholder(body, "ABSTRACT_CN", _front_matter_value(model, "chinese_abstract", "abstract_cn", "cn_abstract"))
    _replace_block_placeholder(body, "ABSTRACT_EN", _front_matter_value(model, "english_abstract", "abstract_en", "en_abstract"))
    _replace_block_placeholder(body, "TASK_RAW_MATERIALS", _front_matter_value(model, "task_raw_materials"))
    _replace_block_placeholder(body, "TASK_WORK_CONTENT", _front_matter_value(model, "task_work_content"))
    _replace_block_placeholder(body, "TASK_REFERENCES", _front_matter_value(model, "task_references"))
    _replace_block_placeholder(body, "ACKNOWLEDGEMENT", _front_matter_value(model, "acknowledgement", "acknowledgements"))
    _replace_block_placeholder(body, "REFERENCES", "\n".join(_block_text(reference) for reference in model.references))
    _remove_empty_placeholders(root)
    _assert_no_forbidden_text(root)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _replace_body_range(body: etree._Element, model: ThesisModel, style_map: dict[str, str]) -> None:
    children = list(body)
    start = _index_of_paragraph_containing(children, "{{BODY_START}}")
    end = _index_of_paragraph_containing(children, "{{BODY_END}}")
    if start is None or end is None or end < start:
        return

    body_blocks = _body_elements(model, style_map)
    for child in children[start : end + 1]:
        body.remove(child)
    insert_at = start
    for offset, paragraph in enumerate(body_blocks):
        body.insert(insert_at + offset, paragraph)


def _replace_block_placeholder(body: etree._Element, placeholder: str, text: str) -> None:
    marker = f"{{{{{placeholder}}}}}"
    template = _paragraph_containing(body, marker)
    if template is None:
        return
    parent = template.getparent()
    if parent is None:
        return
    index = parent.index(template)
    parent.remove(template)
    replacement_paragraphs = _paragraphs_from_template(template, text)
    for offset, paragraph in enumerate(replacement_paragraphs):
        parent.insert(index + offset, paragraph)


def _paragraphs_from_template(template: etree._Element, text: str) -> list[etree._Element]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        lines = [""]
    paragraphs: list[etree._Element] = []
    for line in lines:
        paragraph = deepcopy(template)
        _set_paragraph_text(paragraph, line)
        paragraphs.append(paragraph)
    return paragraphs


def _body_elements(model: ThesisModel, style_map: dict[str, str]) -> list[etree._Element]:
    elements: list[etree._Element] = []
    for section in model.sections:
        title = str(section.title or "").strip()
        if title:
            elements.append(_styled_paragraph(title, _style_for_block(section, style_map)))
        for line in str(section.text or "").splitlines():
            text = line.strip()
            if text:
                elements.append(_styled_paragraph(text, style_map.get("body", "a")))
    for table in model.tables:
        if table.title:
            elements.append(_styled_paragraph(table.title, style_map.get("caption_table", "af0")))
        elements.append(_table_element(table.text))
    for equation in model.equations:
        if equation.omml.strip():
            elements.append(_omml_element(equation.omml))
        elif equation.text.strip():
            elements.append(_styled_paragraph(equation.text, style_map.get("body", "a")))
    if not elements:
        elements.append(_styled_paragraph("", style_map.get("body", "a")))
    return elements


def _styled_paragraph(text: str, style_id: str) -> etree._Element:
    p = etree.Element(f"{{{W_NS}}}p")
    if style_id:
        p_pr = etree.SubElement(p, f"{{{W_NS}}}pPr")
        etree.SubElement(p_pr, f"{{{W_NS}}}pStyle").set(f"{{{W_NS}}}val", style_id)
    run = etree.SubElement(p, f"{{{W_NS}}}r")
    text_node = etree.SubElement(run, f"{{{W_NS}}}t")
    if text.startswith(" ") or text.endswith(" "):
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = text
    return p


def _table_element(text: str) -> etree._Element:
    table = etree.Element(f"{{{W_NS}}}tbl")
    rows = _table_rows(text)
    for row in rows:
        tr = etree.SubElement(table, f"{{{W_NS}}}tr")
        for value in row:
            tc = etree.SubElement(tr, f"{{{W_NS}}}tc")
            tc_pr = etree.SubElement(tc, f"{{{W_NS}}}tcPr")
            etree.SubElement(tc_pr, f"{{{W_NS}}}tcW").set(f"{{{W_NS}}}type", "auto")
            paragraph = etree.SubElement(tc, f"{{{W_NS}}}p")
            run = etree.SubElement(paragraph, f"{{{W_NS}}}r")
            text_node = etree.SubElement(run, f"{{{W_NS}}}t")
            text_node.text = value
    return table


def _table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "\t" in stripped:
            rows.append([cell.strip() for cell in stripped.split("\t")])
        else:
            rows.append([cell.strip() for cell in stripped.split("|") if cell.strip()] or [stripped])
    return rows or [[""]]


def _omml_element(omml: str) -> etree._Element:
    try:
        return etree.fromstring(omml.encode("utf-8"))
    except etree.XMLSyntaxError:
        return _styled_paragraph(omml, "a")


def _style_for_block(block: ContentBlock, style_map: dict[str, str]) -> str:
    if block.level <= 1 or block.type == "chapter":
        return style_map.get("chapter", "1")
    if block.level == 2 or block.type == "section":
        return style_map.get("section", "2")
    return style_map.get("subsection", "3")


def _set_paragraph_text(paragraph: etree._Element, text: str) -> None:
    text_nodes = [node for node in paragraph.iter() if node.tag in TEXT_TAGS]
    if not text_nodes:
        run = etree.SubElement(paragraph, f"{{{W_NS}}}r")
        text_node = etree.SubElement(run, f"{{{W_NS}}}t")
        text_node.text = text
        return
    text_nodes[0].text = text
    for node in text_nodes[1:]:
        node.text = ""


def _index_of_paragraph_containing(children: list[etree._Element], text: str) -> int | None:
    for index, child in enumerate(children):
        if child.tag == f"{{{W_NS}}}p" and text in _element_text(child):
            return index
    return None


def _paragraph_containing(root: etree._Element, text: str) -> etree._Element | None:
    for paragraph in root.findall(".//w:p", NS):
        if text in _element_text(paragraph):
            return paragraph
    return None


def _element_text(element: etree._Element) -> str:
    return "".join((node.text or "") for node in element.iter() if node.tag in TEXT_TAGS)


def _remove_empty_placeholders(root: etree._Element) -> None:
    for node in root.iter():
        if node.tag in TEXT_TAGS and node.text and "{{" in node.text and "}}" in node.text:
            for placeholder in BLOCK_PLACEHOLDERS:
                node.text = node.text.replace(f"{{{{{placeholder}}}}}", "")
            if "{{" in node.text and "}}" in node.text:
                node.text = ""


def _assert_no_forbidden_text(root: etree._Element) -> None:
    visible_text = "\n".join((node.text or "") for node in root.iter() if node.tag in TEXT_TAGS)
    for marker in FORBIDDEN_BODY_TEXT:
        if marker in visible_text:
            raise ValueError(f"Forbidden final Word text detected: {marker}")


def _front_matter_value(model: ThesisModel, *keys: str) -> str:
    for key in keys:
        value = model.front_matter.get(key)
        if value:
            return str(value)
    return ""


def _block_text(block: ContentBlock) -> str:
    return "\n".join(part for part in (block.title, block.text) if part).strip()


def _split_title(title: str) -> tuple[str, str]:
    value = str(title or "").strip()
    if not value:
        return "", ""
    if len(value) <= 18:
        return value, ""
    break_at = min(max(len(value) // 2, 12), 24)
    return value[:break_at], value[break_at:]


def _load_style_map(style_map_path: Path | None) -> dict[str, str]:
    default = {
        "chapter": "1",
        "section": "2",
        "subsection": "3",
        "body": "a",
        "caption_figure": "af0",
        "caption_table": "af0",
        "reference": "a",
    }
    if style_map_path is None or not Path(style_map_path).exists():
        return default
    try:
        loaded = json.loads(Path(style_map_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return {**default, **{key: str(value) for key, value in loaded.items()}}


__all__ = ["assemble_in_place"]
