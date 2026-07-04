from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from copy import deepcopy
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
DEFAULT_INPUT = ROOT / "templates" / "official" / "buaa_undergraduate_template.docx"
DEFAULT_OUTPUT = ROOT / "templates" / "official" / "buaa_undergraduate_template_instrumented.docx"
REQUIRED_PLACEHOLDERS = {
    "UNIT_CODE",
    "STUDENT_ID",
    "CLASSIFICATION",
    "TITLE_CN_LINE1",
    "TITLE_CN_LINE2",
    "COLLEGE",
    "MAJOR",
    "STUDENT_NAME",
    "ADVISOR",
    "DATE_YEAR_MONTH",
    "SPINE_TITLE_CN",
    "SPINE_STUDENT_NAME",
    "SPINE_UNIVERSITY",
    "TASK_TITLE",
    "TASK_RAW_MATERIALS",
    "TASK_WORK_CONTENT",
    "TASK_REFERENCES",
    "TASK_COLLEGE_MAJOR_CLASS",
    "TASK_STUDENT_NAME",
    "TASK_DATE_RANGE",
    "TASK_DEFENSE_DATE",
    "TASK_GRADE",
    "TASK_ADVISOR",
    "TASK_DIRECTOR_SIGNATURE",
    "DECLARATION_STUDENT_NAME",
    "DECLARATION_DATE",
    "TITLE_CN",
    "ABSTRACT_CN",
    "KEYWORDS_CN",
    "TITLE_EN",
    "AUTHOR_EN",
    "TUTOR_EN",
    "ABSTRACT_EN",
    "KEYWORDS_EN",
    "BODY_START",
    "BODY_END",
    "REFERENCES",
    "ACKNOWLEDGEMENT",
}


def instrument_official_template(template_path: Path, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Insert in-place placeholders into the official template without splitting it."""
    source = Path(template_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source, "r") as package:
        root = etree.fromstring(
            package.read("word/document.xml"),
            etree.XMLParser(remove_blank_text=False, resolve_entities=False),
        )

    body = root.find("w:body", NS)
    if body is None:
        raise ValueError(f"Invalid official template: missing word/body: {source}")

    replacements = _instrument_known_regions(body)
    _ensure_toc_field(body)
    _instrument_body_range(body)
    document_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    all_placeholders = set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", document_xml.decode("utf-8", errors="ignore")))
    missing_placeholders = sorted(REQUIRED_PLACEHOLDERS - all_placeholders)

    with tempfile.TemporaryDirectory(prefix="buaa_instrument_") as temp_dir:
        temp_output = Path(temp_dir) / "instrumented.docx"
        with zipfile.ZipFile(source, "r") as src, zipfile.ZipFile(temp_output, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                data = document_xml if item.filename == "word/document.xml" else src.read(item.filename)
                dst.writestr(item, data)
        shutil.move(str(temp_output), str(output))

    report = {
        "status": "pass" if not missing_placeholders else "failed",
        "created_from": str(source),
        "output": str(output),
        "instrumented_placeholders": sorted(all_placeholders),
        "missing_placeholders": missing_placeholders,
        "template_mode": "in_place",
        "fragment_assembly": False,
    }
    (output.parent / "instrument_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _instrument_known_regions(body: etree._Element) -> set[str]:
    paragraphs = body.findall(".//w:p", NS)
    texts = [_element_text(paragraph) for paragraph in paragraphs]
    replacements: set[str] = set()

    rules = [
        ("单位代码", "单位代码       {{UNIT_CODE}}"),
        ("学    号", "学    号     {{STUDENT_ID}}"),
        ("分类号", "分类号    {{CLASSIFICATION}}"),
        ("（题目）", "{{TITLE_CN_LINE1}}"),
        ("学院名称", "学院名称"),
        ("电子信息工程学院", "{{COLLEGE}}"),
        ("专业名称", "专业名称"),
        ("电子与信息技术", "{{MAJOR}}"),
        ("学生姓名", "学生姓名"),
        ("李兴新", "{{STUDENT_NAME}}"),
        ("指导教师", "指导教师"),
        ("毛  峡", "{{ADVISOR}}"),
        ("2015年6月", "{{DATE_YEAR_MONTH}}"),
        ("论文题目姓名北京航空航天大学", "{{SPINE_TITLE_CN}}{{SPINE_STUDENT_NAME}}{{SPINE_UNIVERSITY}}"),
        ("Ⅰ、毕业设计（论文）题目：", "Ⅰ、毕业设计（论文）题目：{{TASK_TITLE}}"),
        (
            "Ⅱ、毕业设计（论文）使用的原始资料（数据）及设计技术要求：",
            "Ⅱ、毕业设计（论文）使用的原始资料（数据）及设计技术要求：{{TASK_RAW_MATERIALS}}",
        ),
        ("Ⅲ、毕业设计（论文）工作内容：", "Ⅲ、毕业设计（论文）工作内容：{{TASK_WORK_CONTENT}}"),
        ("Ⅳ、主要参考资料：", "Ⅳ、主要参考资料：{{TASK_REFERENCES}}"),
        ("学院（系）", "学院（系）{{TASK_COLLEGE_MAJOR_CLASS}}"),
        ("学生", "学生                      {{TASK_STUDENT_NAME}}"),
        ("毕业设计（论文）时间：", "毕业设计（论文）时间：{{TASK_DATE_RANGE}}"),
        ("答辩时间：", "答辩时间：{{TASK_DEFENSE_DATE}}"),
        ("成    绩：", "成    绩：{{TASK_GRADE}}"),
        ("指导教师：", "指导教师：{{TASK_ADVISOR}}"),
        ("系（教研室） 主任（签字）：", "系（教研室） 主任（签字）：{{TASK_DIRECTOR_SIGNATURE}}"),
        ("作者：王小亮", "作者：{{DECLARATION_STUDENT_NAME}}"),
        ("时间：2015年 6 月", "时间：{{DECLARATION_DATE}}"),
        ("油/水电迁移微观动态过程的研究", "{{TITLE_CN}}"),
        ("学生：黄  欣", "学    生：{{STUDENT_NAME}}"),
        ("指导教师：朱岳麟", "指导教师：{{ADVISOR}}"),
        ("电分离工艺技术在炼油工业中是效率最好", "{{ABSTRACT_CN}}"),
        ("关键词：高频高压，油/水电迁移", "关键词：{{KEYWORDS_CN}}"),
        ("Micro-process of Oil/Water Transferring in Electric Field", "{{TITLE_EN}}"),
        ("Author : HUANG Xin", "Author : {{AUTHOR_EN}}"),
        ("Tutor : ZHU Yue-lin", "Tutor : {{TUTOR_EN}}"),
        ("Electro-desalting is the most efficient", "{{ABSTRACT_EN}}"),
        ("Key words：High-frequency high-voltage", "Key words：{{KEYWORDS_EN}}"),
    ]

    used_indexes: set[int] = set()
    for needle, replacement in rules:
        index = _find_first_index(texts, needle, used_indexes)
        if index is None:
            continue
        _set_paragraph_text(paragraphs[index], replacement)
        texts[index] = replacement
        used_indexes.add(index)
        replacements.update(_placeholders_in_text(replacement))
        if replacement == "{{TITLE_CN_LINE1}}":
            clone = deepcopy(paragraphs[index])
            _set_paragraph_text(clone, "{{TITLE_CN_LINE2}}")
            parent = paragraphs[index].getparent()
            parent.insert(parent.index(paragraphs[index]) + 1, clone)
            replacements.add("TITLE_CN_LINE2")

    return replacements


def _ensure_toc_field(body: etree._Element) -> None:
    toc_paragraph = _find_toc_paragraph(body)
    if toc_paragraph is None:
        return
    if _children_have_field([toc_paragraph]):
        return
    toc_paragraph.append(_toc_field())


def _instrument_body_range(body: etree._Element) -> None:
    children = [child for child in body if child.tag == f"{{{W_NS}}}p"]
    toc_index = _find_toc_paragraph_index(children)
    body_start = _find_body_start(children, toc_index)
    if body_start is None:
        return
    reference_index = _find_reference_index(children, body_start)
    if reference_index is None:
        reference_index = len(children)

    body_start_marker = _clone_marker(children[body_start], "{{BODY_START}}")
    body_end_marker = _clone_marker(children[body_start], "{{BODY_END}}")
    parent = children[body_start].getparent()
    parent.insert(parent.index(children[body_start]), body_start_marker)

    refreshed_children = [child for child in body if child.tag == f"{{{W_NS}}}p"]
    refreshed_reference = _find_reference_index(refreshed_children, body_start + 1)
    if refreshed_reference is None:
        refreshed_reference = len(refreshed_children) - 1
    parent.insert(parent.index(refreshed_children[refreshed_reference]), body_end_marker)

    refreshed_children = [child for child in body if child.tag == f"{{{W_NS}}}p"]
    refreshed_reference = _find_reference_index(refreshed_children, body_start + 1)
    if refreshed_reference is not None:
        insert_at = refreshed_reference + 1
        reference_placeholder = _clone_marker(refreshed_children[refreshed_reference], "{{REFERENCES}}")
        parent.insert(parent.index(refreshed_children[refreshed_reference]) + 1, reference_placeholder)
        acknowledgement_title = _clone_marker(refreshed_children[refreshed_reference], "致谢")
        acknowledgement_body = _clone_marker(refreshed_children[refreshed_reference], "{{ACKNOWLEDGEMENT}}")
        parent.insert(parent.index(refreshed_children[refreshed_reference]), acknowledgement_title)
        parent.insert(parent.index(refreshed_children[refreshed_reference]), acknowledgement_body)


def _find_body_start(paragraphs: list[etree._Element], toc_index: int | None) -> int | None:
    start = (toc_index + 1) if toc_index is not None else 0
    for index in range(start, len(paragraphs)):
        text = _element_text(paragraphs[index]).strip()
        if _looks_like_manual_toc(text):
            continue
        if _paragraph_style(paragraphs[index]) in {"1", "Heading1"}:
            return index
    return None


def _find_reference_index(paragraphs: list[etree._Element], start: int) -> int | None:
    for index in range(start, len(paragraphs)):
        text = _element_text(paragraphs[index]).strip()
        if text == "参考文献":
            return index
    return None


def _clone_marker(template: etree._Element, marker: str) -> etree._Element:
    clone = deepcopy(template)
    _set_paragraph_text(clone, marker)
    return clone


def _find_first_index(texts: list[str], needle: str, used_indexes: set[int]) -> int | None:
    normalized_needle = _normalize(needle)
    for index, text in enumerate(texts):
        if index in used_indexes:
            continue
        if normalized_needle and normalized_needle in _normalize(text):
            return index
    return None


def _find_paragraph(body: etree._Element, needle: str) -> etree._Element | None:
    for child in body.findall(".//w:p", NS):
        if child.tag == f"{{{W_NS}}}p" and needle in _element_text(child):
            return child
    return None


def _find_toc_paragraph(body: etree._Element) -> etree._Element | None:
    for paragraph in body.findall(".//w:p", NS):
        if _is_toc_title_text(_element_text(paragraph)):
            return paragraph
    return None


def _find_toc_paragraph_index(paragraphs: list[etree._Element]) -> int | None:
    for index, paragraph in enumerate(paragraphs):
        if _is_toc_title_text(_element_text(paragraph)):
            return index
    return None


def _is_toc_title_text(text: str) -> bool:
    normalized = _normalize(text)
    return normalized == "目录" or normalized.startswith("目录toc")


def _find_paragraph_index(paragraphs: list[etree._Element], needle: str) -> int | None:
    for index, paragraph in enumerate(paragraphs):
        if needle in _element_text(paragraph):
            return index
    return None


def _paragraph_style(paragraph: etree._Element) -> str:
    style = paragraph.find("w:pPr/w:pStyle", NS)
    return style.get(f"{{{W_NS}}}val", "") if style is not None else ""


def _looks_like_manual_toc(text: str) -> bool:
    stripped = text.strip()
    return "…" in stripped or "..." in stripped or stripped in {"TOC1", "1"}


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


def _toc_field() -> etree._Element:
    return etree.fromstring(
        (
            f'<w:fldSimple xmlns:w="{W_NS}" w:instr="TOC \\o &quot;1-3&quot; \\h \\z \\u">'
            "<w:r><w:t>TOC</w:t></w:r>"
            "</w:fldSimple>"
        ).encode("utf-8")
    )


def _children_have_field(children: list[etree._Element]) -> bool:
    return any("fldSimple" in etree.tostring(child, encoding="unicode") or "instrText" in etree.tostring(child, encoding="unicode") for child in children)


def _element_text(element: etree._Element) -> str:
    return "".join((node.text or "") for node in element.iter() if node.tag in TEXT_TAGS)


def _normalize(text: str) -> str:
    return "".join(str(text or "").split()).lower()


def _placeholders_in_text(text: str) -> set[str]:
    result: set[str] = set()
    for chunk in text.split("{{")[1:]:
        name = chunk.split("}}", 1)[0]
        if name:
            result.add(name)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instrument the official BUAA template for in-place filling.")
    parser.add_argument("--template", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = instrument_official_template(args.template, args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
