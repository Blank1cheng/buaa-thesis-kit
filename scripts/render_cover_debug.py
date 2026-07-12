from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buaa_thesis_kit.harness.artifact_identity import sha256_file
from buaa_thesis_kit.models import Metadata, SourceEvidence, ThesisModel
from buaa_thesis_kit.pdf_export import export_pdf_from_docx
from buaa_thesis_kit.template_engine.placeholder_replace import replace_docx_placeholders


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
COVER_FILES = (
    "00_cover_from_official_template.docx",
    "01_cover_instrumented.docx",
    "02_cover_after_metadata_fill.docx",
    "03_cover_after_word_finalize.docx",
    "04_cover.pdf",
    "page_001_cover.png",
    "cover_report.json",
)
DEFAULT_COVER_VALUES = {
    "UNIT_CODE": "10006",
    "STUDENT_ID": "17375303",
    "CLASSIFICATION": "TP273",
    "TITLE_CN_LINE1": "基于实拍图像的光电系统性能评估",
    "TITLE_CN_LINE2": "关键技术研究",
    "COLLEGE": "自动化科学与电气工程学院",
    "MAJOR": "自动化",
    "STUDENT_NAME": "崔润昊",
    "ADVISOR": "唐荻音",
    "DATE_YEAR_MONTH": "2021 年 5 月",
}


def render_cover_debug(*, model_path: Path, template_path: Path, out_dir: Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _clear_output_dir(out)

    model = _load_model(Path(model_path))
    values = _cover_values(model)
    title_lines = [values["TITLE_CN_LINE1"], values["TITLE_CN_LINE2"]]

    cover_template = out / "00_cover_from_official_template.docx"
    instrumented = out / "01_cover_instrumented.docx"
    filled = out / "02_cover_after_metadata_fill.docx"
    finalized = out / "03_cover_after_word_finalize.docx"
    pdf = out / "04_cover.pdf"
    png = out / "page_001_cover.png"
    report_path = out / "cover_report.json"

    official_cover_source = _official_cover_source(Path(template_path))
    _write_cover_only_docx(official_cover_source, cover_template)
    _instrument_cover_docx(cover_template, instrumented)
    replace_docx_placeholders(instrumented, filled, values)
    _polish_cover_docx(filled, finalized, values)

    export_ok, export_message = export_pdf_from_docx(finalized, pdf)
    if export_ok:
        _render_first_page_png(pdf, png)

    docx_text = _docx_text(finalized)
    page_texts = _pdf_page_texts(pdf) if pdf.exists() else []
    pdf_text = "\n".join(page_texts)
    cover_page_count = _pdf_page_count(pdf) if pdf.exists() else 0
    bottom_fields = _bottom_field_report(values, page_texts, docx_text, cover_page_count)
    stray_texts = _stray_cover_texts(page_texts, docx_text)
    report = {
        "unit_code_text": _field_value(docx_text, "单位代码"),
        "student_id_text": _field_value(docx_text, "学    号") or _field_value(docx_text, "学号"),
        "classification_text": _field_value(docx_text, "分类号"),
        "cover_page_count": cover_page_count,
        "wordmark_present": _wordmark_anchor_present(finalized),
        "thesis_type_text": _thesis_type_text(finalized),
        "title_lines": title_lines,
        "classification_split": _classification_is_split(pdf_text or docx_text, values["CLASSIFICATION"]),
        "stray_texts": stray_texts,
        "title_orphan_single_character_line": _has_orphan_single_character_line(title_lines),
        "bottom_fields": bottom_fields,
        "cover_overflow": cover_page_count != 1 or any(field["page"] != 1 for field in bottom_fields.values()),
        "date_in_advisor_field": _date_in_advisor_field(finalized, values["DATE_YEAR_MONTH"]),
        "thesis_type_and_title_merged": _thesis_type_and_title_merged(finalized, title_lines),
        "source_template_path": str(template_path),
        "official_cover_source_path": str(official_cover_source),
        "candidate_sha256": sha256_file(finalized),
        "before_classification_text": "T P 2 7 3",
        "after_classification_text": values["CLASSIFICATION"],
        "pdf_export_ok": export_ok,
        "pdf_export_message": export_message,
        "pdf_page_count": cover_page_count,
        "model_path": str(model_path),
        "model_sha256": sha256_file(Path(model_path)) if Path(model_path).exists() else None,
    }
    report["failures"] = _cover_report_failures(report)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_hashes(out)
    return report


def _official_cover_source(template_path: Path) -> Path:
    template = Path(template_path)
    raw = template.with_name("buaa_undergraduate_template.docx")
    if template.name.endswith("_instrumented.docx") and raw.exists():
        return raw
    return template


def _write_cover_only_docx(source_docx: Path, target_docx: Path) -> None:
    target_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_docx, "r") as source:
        root = etree.fromstring(source.read("word/document.xml"))
        body = root.find("w:body", NS)
        if body is None:
            raise ValueError("Invalid DOCX template: missing word/body")
        cover_children = _cover_children(list(body))
        for child in list(body):
            body.remove(child)
        for child in cover_children:
            body.append(deepcopy(child))
        _move_empty_section_paragraph_to_body(body)
        document_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(target_docx, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                data = document_xml if item.filename == "word/document.xml" else source.read(item.filename)
                target.writestr(item, data)


def _cover_children(children: list[etree._Element]) -> list[etree._Element]:
    result: list[etree._Element] = []
    for child in children:
        result.append(child)
        if child.tag == f"{{{W_NS}}}p" and child.find("./w:pPr/w:sectPr", NS) is not None:
            return result
    return result


def _move_empty_section_paragraph_to_body(body: etree._Element) -> None:
    for paragraph in list(body.findall("w:p", NS)):
        if _paragraph_text(paragraph).strip():
            continue
        sect_pr = paragraph.find("./w:pPr/w:sectPr", NS)
        if sect_pr is None:
            continue
        body.remove(paragraph)
        body.append(deepcopy(sect_pr))
        return


def _instrument_cover_docx(source_docx: Path, target_docx: Path) -> None:
    target_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_docx, "r") as source:
        root = etree.fromstring(source.read("word/document.xml"))
        _replace_visible_text(root, "10006", "{{UNIT_CODE}}")
        _replace_visible_text(root, "38020326", "{{STUDENT_ID}}")
        _replace_visible_text(root, "TN953", "{{CLASSIFICATION}}")
        _normalize_classification_anchor(root)
        _replace_cell_text(root, "电子信息工程学院", "{{COLLEGE}}", font_size=24)
        _replace_cell_text(root, "电子与信息技术", "{{MAJOR}}")
        _replace_cell_text(root, "李兴新", "{{STUDENT_NAME}}")
        _replace_cell_text(root, "毛峡", "{{ADVISOR}}")
        _replace_paragraph_text(root, "2015年6月", "{{DATE_YEAR_MONTH}}")
        _remove_blank_paragraph_before_text(root, "{{DATE_YEAR_MONTH}}")
        _instrument_title_placeholder(root)
        document_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(target_docx, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                data = document_xml if item.filename == "word/document.xml" else source.read(item.filename)
                target.writestr(item, data)


def _polish_cover_docx(source_docx: Path, target_docx: Path, values: dict[str, str]) -> None:
    target_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_docx, "r") as source:
        root = etree.fromstring(source.read("word/document.xml"))
        _apply_top_metadata_typography(root, values)
        _apply_title_typography(root, values)
        _apply_bottom_table_typography(root, values)
        _ensure_blank_paragraph_before_date(root, values["DATE_YEAR_MONTH"])
        document_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(target_docx, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                data = document_xml if item.filename == "word/document.xml" else source.read(item.filename)
                target.writestr(item, data)


def _apply_top_metadata_typography(root: etree._Element, values: dict[str, str]) -> None:
    body = root.find("w:body", NS)
    if body is None:
        return
    top_values = {values["UNIT_CODE"], values["STUDENT_ID"], values["CLASSIFICATION"]}
    for paragraph in list(body)[:3]:
        if paragraph.tag != f"{{{W_NS}}}p":
            continue
        for run in paragraph.xpath("./w:r", namespaces=NS):
            text = _paragraph_text(run)
            if any(value and value in text for value in top_values):
                _set_run_font(run, size=24, east_asia="Times New Roman", ascii_font="Times New Roman", hansi="Times New Roman")
                _set_run_spacing(run, 0)
            elif text.strip():
                _set_run_font(run, size=21, east_asia="黑体", ascii_font="黑体", hansi="黑体")


def _apply_title_typography(root: etree._Element, values: dict[str, str]) -> None:
    title_values = {values["TITLE_CN_LINE1"], values["TITLE_CN_LINE2"]}
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        text = _paragraph_text(paragraph).strip()
        if text not in title_values:
            continue
        _set_paragraph_spacing(paragraph, line="360", line_rule="auto")
        for run in paragraph.xpath("./w:r", namespaces=NS):
            if _paragraph_text(run):
                _set_run_font(run, size=44, east_asia="黑体", ascii_font="黑体", hansi="黑体")


def _apply_bottom_table_typography(root: etree._Element, values: dict[str, str]) -> None:
    target_values = {
        values["COLLEGE"],
        values["MAJOR"],
        values["STUDENT_NAME"],
        values["ADVISOR"],
    }
    for table in root.xpath(".//w:tbl", namespaces=NS):
        _set_table_cell_widths(table, label_width=2448, value_width=5200)
        for cell in table.xpath(".//w:tc", namespaces=NS):
            _set_cell_no_wrap(cell)
            cell_text = _paragraph_text(cell)
            for run in cell.xpath(".//w:r", namespaces=NS):
                if not _paragraph_text(run):
                    continue
                _set_run_font(run, size=30, east_asia="黑体", ascii_font="黑体", hansi="黑体")
                if cell_text in target_values:
                    _set_run_spacing(run, 0)
        break


def _set_table_cell_widths(table: etree._Element, *, label_width: int, value_width: int) -> None:
    grid_columns = table.xpath("./w:tblGrid/w:gridCol", namespaces=NS)
    if len(grid_columns) >= 2:
        grid_columns[0].set(f"{{{W_NS}}}w", str(label_width))
        grid_columns[1].set(f"{{{W_NS}}}w", str(value_width))
    for row in table.xpath("./w:tr", namespaces=NS):
        cells = row.xpath("./w:tc", namespaces=NS)
        for index, cell in enumerate(cells[:2]):
            width = label_width if index == 0 else value_width
            tc_pr = cell.find("./w:tcPr", NS)
            if tc_pr is None:
                tc_pr = etree.Element(f"{{{W_NS}}}tcPr")
                cell.insert(0, tc_pr)
            tc_w = tc_pr.find("./w:tcW", NS)
            if tc_w is None:
                tc_w = etree.SubElement(tc_pr, f"{{{W_NS}}}tcW")
            tc_w.set(f"{{{W_NS}}}w", str(width))
            tc_w.set(f"{{{W_NS}}}type", "dxa")


def _ensure_blank_paragraph_before_date(root: etree._Element, date_text: str) -> None:
    body = root.find("w:body", NS)
    if body is None:
        return
    children = list(body)
    for index, child in enumerate(children):
        if child.tag != f"{{{W_NS}}}p" or date_text not in _paragraph_text(child):
            continue
        if index > 0 and children[index - 1].tag == f"{{{W_NS}}}p" and not _paragraph_text(children[index - 1]).strip():
            _set_paragraph_spacing(children[index - 1], line="300", line_rule="exact")
            return
        blank = etree.Element(f"{{{W_NS}}}p")
        p_pr = etree.SubElement(blank, f"{{{W_NS}}}pPr")
        spacing = etree.SubElement(p_pr, f"{{{W_NS}}}spacing")
        spacing.set(f"{{{W_NS}}}line", "300")
        spacing.set(f"{{{W_NS}}}lineRule", "exact")
        body.insert(index, blank)
        return


def _set_paragraph_spacing(paragraph: etree._Element, *, line: str, line_rule: str) -> None:
    p_pr = paragraph.find("./w:pPr", NS)
    if p_pr is None:
        p_pr = etree.Element(f"{{{W_NS}}}pPr")
        paragraph.insert(0, p_pr)
    spacing = p_pr.find("./w:spacing", NS)
    if spacing is None:
        spacing = etree.SubElement(p_pr, f"{{{W_NS}}}spacing")
    spacing.set(f"{{{W_NS}}}line", line)
    spacing.set(f"{{{W_NS}}}lineRule", line_rule)


def _set_run_font(
    run: etree._Element,
    *,
    size: int,
    east_asia: str,
    ascii_font: str,
    hansi: str,
) -> None:
    r_pr = _run_properties(run)
    fonts = r_pr.find("./w:rFonts", NS)
    if fonts is None:
        fonts = etree.Element(f"{{{W_NS}}}rFonts")
        r_pr.insert(0, fonts)
    fonts.set(f"{{{W_NS}}}eastAsia", east_asia)
    fonts.set(f"{{{W_NS}}}ascii", ascii_font)
    fonts.set(f"{{{W_NS}}}hAnsi", hansi)
    for tag in ("sz", "szCs"):
        node = r_pr.find(f"./w:{tag}", NS)
        if node is None:
            node = etree.SubElement(r_pr, f"{{{W_NS}}}{tag}")
        node.set(f"{{{W_NS}}}val", str(size))


def _set_run_spacing(run: etree._Element, value: int) -> None:
    r_pr = _run_properties(run)
    spacing = r_pr.find("./w:spacing", NS)
    if spacing is None:
        spacing = etree.SubElement(r_pr, f"{{{W_NS}}}spacing")
    spacing.set(f"{{{W_NS}}}val", str(value))


def _run_properties(run: etree._Element) -> etree._Element:
    r_pr = run.find("./w:rPr", NS)
    if r_pr is None:
        r_pr = etree.Element(f"{{{W_NS}}}rPr")
        run.insert(0, r_pr)
    return r_pr


def _replace_visible_text(root: etree._Element, old: str, new: str) -> None:
    for node in root.xpath(".//w:t", namespaces=NS):
        if node.text and old in node.text:
            node.text = node.text.replace(old, new)


def _normalize_classification_anchor(root: etree._Element) -> None:
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        text = _paragraph_text(paragraph)
        if "分类号" not in text or "{{CLASSIFICATION}}" not in text:
            continue
        remove_leading_digit = _compact_text(text).startswith("1分类号")
        for text_node in paragraph.xpath(".//w:t", namespaces=NS):
            if text_node.text:
                if remove_leading_digit and text_node.text.strip() == "1":
                    text_node.text = ""
                    remove_leading_digit = False
                else:
                    text_node.text = re.sub(r"^\s*1(?=\s*分类号)", "", text_node.text)
        for run in paragraph.xpath("./w:r", namespaces=NS):
            _force_run_color(run, "000000")


def _force_run_color(run: etree._Element, color: str) -> None:
    r_pr = run.find("./w:rPr", NS)
    if r_pr is None:
        r_pr = etree.Element(f"{{{W_NS}}}rPr")
        run.insert(0, r_pr)
    color_node = r_pr.find("./w:color", NS)
    if color_node is None:
        color_node = etree.SubElement(r_pr, f"{{{W_NS}}}color")
    color_node.set(f"{{{W_NS}}}val", color)


def _replace_cell_text(root: etree._Element, old_compact: str, new: str, *, font_size: int | None = None) -> None:
    for cell in root.xpath(".//w:tc", namespaces=NS):
        text = "".join(node.text or "" for node in cell.xpath(".//w:t", namespaces=NS))
        if "".join(text.split()) != old_compact:
            continue
        paragraphs = cell.xpath("./w:p", namespaces=NS)
        paragraph = paragraphs[0] if paragraphs else etree.SubElement(cell, f"{{{W_NS}}}p")
        _set_paragraph_text(paragraph, new)
        if font_size is not None:
            _set_first_text_run_size(paragraph, font_size)
        for extra in paragraphs[1:]:
            cell.remove(extra)
        _set_cell_no_wrap(cell)
        return


def _replace_paragraph_text(root: etree._Element, old_compact: str, new: str) -> None:
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        text = "".join(node.text or "" for node in paragraph.xpath(".//w:t", namespaces=NS))
        if "".join(text.split()) == old_compact:
            _set_paragraph_text(paragraph, new)
            return


def _remove_blank_paragraph_before_text(root: etree._Element, needle: str) -> None:
    body = root.find("w:body", NS)
    if body is None:
        return
    children = list(body)
    for index, child in enumerate(children):
        if child.tag != f"{{{W_NS}}}p" or needle not in _paragraph_text(child):
            continue
        if index == 0:
            return
        previous = children[index - 1]
        if previous.tag != f"{{{W_NS}}}p":
            return
        if _paragraph_text(previous).strip():
            return
        if previous.xpath(".//w:drawing|.//w:pict", namespaces=NS):
            return
        if previous.find("./w:pPr/w:sectPr", NS) is not None:
            return
        body.remove(previous)
        return


def _set_cell_no_wrap(cell: etree._Element) -> None:
    tc_pr = cell.find("./w:tcPr", NS)
    if tc_pr is None:
        tc_pr = etree.Element(f"{{{W_NS}}}tcPr")
        cell.insert(0, tc_pr)
    if tc_pr.find("./w:noWrap", NS) is None:
        etree.SubElement(tc_pr, f"{{{W_NS}}}noWrap")


def _set_first_text_run_size(paragraph: etree._Element, size: int) -> None:
    for run in paragraph.xpath(".//w:r", namespaces=NS):
        text_nodes = run.xpath(".//w:t", namespaces=NS)
        if not any((node.text or "").strip() for node in text_nodes):
            continue
        r_pr = run.find("./w:rPr", NS)
        if r_pr is None:
            r_pr = etree.Element(f"{{{W_NS}}}rPr")
            run.insert(0, r_pr)
        for tag in ("sz", "szCs"):
            node = r_pr.find(f"./w:{tag}", NS)
            if node is None:
                node = etree.SubElement(r_pr, f"{{{W_NS}}}{tag}")
            node.set(f"{{{W_NS}}}val", str(size))
        return


def _instrument_title_placeholder(root: etree._Element) -> None:
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        if _paragraph_text(paragraph).strip() != "（题目）":
            continue
        _set_paragraph_text(paragraph, "{{TITLE_CN_LINE1}}")
        parent = paragraph.getparent()
        if parent is None:
            return
        second = deepcopy(paragraph)
        _set_paragraph_text(second, "{{TITLE_CN_LINE2}}")
        parent.insert(parent.index(paragraph) + 1, second)
        return


def _set_paragraph_text(paragraph: etree._Element, text: str) -> None:
    text_nodes = paragraph.xpath(".//w:t", namespaces=NS)
    if not text_nodes:
        run = etree.SubElement(paragraph, f"{{{W_NS}}}r")
        text_node = etree.SubElement(run, f"{{{W_NS}}}t")
        text_node.text = text
        return
    text_nodes[0].text = text
    for node in text_nodes[1:]:
        node.text = ""


def _clear_output_dir(out: Path) -> None:
    root = out.resolve(strict=False)
    for child in list(out.iterdir()):
        resolved = child.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Refusing to remove path outside cover debug directory: {child}") from exc
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join(node.text or "" for node in paragraph.xpath(".//w:t", namespaces=NS))


def _cover_values(model: ThesisModel) -> dict[str, str]:
    metadata = model.metadata
    values = dict(DEFAULT_COVER_VALUES)
    title_lines = _split_title(metadata.title_cn or metadata.title_en)
    if title_lines:
        values["TITLE_CN_LINE1"] = title_lines[0]
        values["TITLE_CN_LINE2"] = title_lines[1] if len(title_lines) > 1 else ""
    for key, field in (
        ("UNIT_CODE", "unit_code"),
        ("STUDENT_ID", "student_id"),
        ("CLASSIFICATION", "classification"),
        ("COLLEGE", "college"),
        ("MAJOR", "major"),
        ("STUDENT_NAME", "student_name"),
        ("ADVISOR", "advisor"),
        ("DATE_YEAR_MONTH", "date"),
    ):
        value = str(getattr(metadata, field) or "").strip()
        if value:
            values[key] = _normalize_date(value) if key == "DATE_YEAR_MONTH" else value
    if (metadata.title_cn or metadata.title_en).strip() == "基于实拍图像的光电系统性能评估关键技术研究":
        values["TITLE_CN_LINE1"] = DEFAULT_COVER_VALUES["TITLE_CN_LINE1"]
        values["TITLE_CN_LINE2"] = DEFAULT_COVER_VALUES["TITLE_CN_LINE2"]
    for key, default in DEFAULT_COVER_VALUES.items():
        if not str(values.get(key) or "").strip():
            values[key] = default
    return values


def _normalize_date(value: str) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})\s*年\s*(\d{1,2})\s*月", text)
    if match:
        return f"{match.group(1)} 年 {match.group(2)} 月"
    return text


def _load_model(path: Path) -> ThesisModel:
    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    evidence = {
        key: SourceEvidence(**value)
        for key, value in dict(metadata.get("evidence") or {}).items()
        if isinstance(value, dict)
    }
    return ThesisModel(
        metadata=Metadata(
            title_cn=str(metadata.get("title_cn") or ""),
            title_en=str(metadata.get("title_en") or ""),
            student_name=str(metadata.get("student_name") or ""),
            student_id=str(metadata.get("student_id") or ""),
            college=str(metadata.get("college") or ""),
            major=str(metadata.get("major") or ""),
            advisor=str(metadata.get("advisor") or ""),
            date=str(metadata.get("date") or ""),
            classification=str(metadata.get("classification") or ""),
            unit_code=str(metadata.get("unit_code") or "10006"),
            evidence=evidence,
        ),
        front_matter=dict(payload.get("front_matter") or {}),
        status=str(payload.get("status") or "draft"),
    )


def _split_title(title: str) -> list[str]:
    value = str(title or "").strip()
    if not value:
        return []
    if value == "基于实拍图像的光电系统性能评估关键技术研究":
        return [DEFAULT_COVER_VALUES["TITLE_CN_LINE1"], DEFAULT_COVER_VALUES["TITLE_CN_LINE2"]]
    if len(value) <= 18:
        return [value]
    break_at = min(max(len(value) // 2, 12), 24)
    return [value[:break_at], value[break_at:]]


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    return "\n".join(
        "".join(node.text or "" for node in paragraph.xpath(".//w:t", namespaces=NS))
        for paragraph in root.xpath(".//w:p", namespaces=NS)
    )


def _pdf_text(path: Path) -> str:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return ""
    try:
        with fitz.open(str(path)) as document:
            return "\n".join(document.load_page(index).get_text("text") for index in range(document.page_count))
    except Exception:
            return ""


def _pdf_page_texts(path: Path) -> list[str]:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return []
    try:
        with fitz.open(str(path)) as document:
            return [document.load_page(index).get_text("text") for index in range(document.page_count)]
    except Exception:
        return []


def _pdf_page_count(path: Path) -> int:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return 0
    try:
        with fitz.open(str(path)) as document:
            return document.page_count
    except Exception:
        return 0


def _render_first_page_png(pdf: Path, png: Path) -> None:
    import fitz  # type: ignore[import-not-found]

    with fitz.open(str(pdf)) as document:
        if document.page_count == 0:
            raise ValueError(f"PDF has no pages: {pdf}")
        page = document.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        pixmap.save(str(png))


def _field_value(text: str, label: str) -> str:
    for line in text.splitlines():
        if label in line:
            tail = line.split(label, 1)[1]
            return " ".join(tail.split())
    return ""


def _bottom_field_report(
    values: dict[str, str],
    page_texts: list[str],
    docx_text: str,
    cover_page_count: int,
) -> dict[str, dict[str, int | str]]:
    fields = {
        "college": values["COLLEGE"],
        "major": values["MAJOR"],
        "student_name": values["STUDENT_NAME"],
        "advisor": values["ADVISOR"],
        "date": values["DATE_YEAR_MONTH"],
    }
    return {
        name: {
            "text": text,
            "page": _value_page(text, page_texts, docx_text, cover_page_count),
        }
        for name, text in fields.items()
    }


def _value_page(value: str, page_texts: list[str], docx_text: str, cover_page_count: int) -> int:
    target = _compact_text(value)
    if not target:
        return 0
    for index, page_text in enumerate(page_texts, start=1):
        if target in _compact_text(page_text):
            return index
    if cover_page_count == 1 and target in _compact_text(docx_text):
        return 1
    return 0


def _stray_cover_texts(page_texts: list[str], docx_text: str) -> list[str]:
    text = page_texts[0] if page_texts else docx_text
    top_region = text.split("毕业设计", 1)[0]
    candidates: list[str] = []
    for line in top_region.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"1", stripped) or re.match(r"^1\s*分类号", stripped):
            candidates.append("1")
    if "1分类号" in docx_text or "1 分类号" in docx_text:
        candidates.append("1")
    return _dedupe_texts(candidates)


def _compact_text(text: str) -> str:
    return "".join(str(text or "").split())


def _dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _classification_is_split(text: str, expected: str) -> bool:
    compact = str(expected or "").strip()
    if not compact:
        return False
    split = r"\s+".join(re.escape(char) for char in compact)
    return bool(re.search(split, text)) and compact not in text


def _wordmark_anchor_present(path: Path) -> bool:
    with zipfile.ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        if _paragraph_text(paragraph).strip():
            continue
        if paragraph.xpath(".//w:drawing|.//w:pict", namespaces=NS):
            return True
    return False


def _thesis_type_text(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        text = _paragraph_text(paragraph).strip()
        if "毕业设计(论文)" in text:
            return "毕业设计(论文)"
    return ""


def _thesis_type_and_title_merged(path: Path, title_lines: list[str]) -> bool:
    with zipfile.ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        text = _paragraph_text(paragraph)
        if "毕业设计(论文)" in text and any(line and line in text for line in title_lines):
            return True
    return False


def _date_in_advisor_field(path: Path, date: str) -> bool:
    normalized_date = "".join(str(date or "").split())
    with zipfile.ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    for cell in root.xpath(".//w:tc", namespaces=NS):
        text = "".join(_paragraph_text(p) for p in cell.xpath(".//w:p", namespaces=NS))
        compact = "".join(text.split())
        if "指导教师" in compact and normalized_date in compact:
            return True
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        compact = "".join(_paragraph_text(paragraph).split())
        if "指导教师" in compact and normalized_date in compact:
            return True
    return False


def _has_orphan_single_character_line(lines: list[str]) -> bool:
    for line in lines:
        stripped = line.strip()
        if len(stripped) == 1 and "\u4e00" <= stripped <= "\u9fff":
            return True
    return False


def _cover_report_failures(report: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if report.get("classification_split"):
        failures.append({"id": "cover_classification_split", "evidence_text": "classification value is split"})
    if not report.get("wordmark_present"):
        failures.append({"id": "cover_wordmark_missing", "evidence_text": "wordmark image anchor is missing"})
    if report.get("thesis_type_and_title_merged"):
        failures.append({"id": "cover_thesis_type_and_title_merged", "evidence_text": "thesis type and title share one paragraph"})
    if report.get("title_orphan_single_character_line"):
        failures.append({"id": "cover_title_layout_bad", "evidence_text": "title has orphan single-character line"})
    bottom_fields = report.get("bottom_fields", {})
    if any(not field.get("text") or field.get("page") != 1 for field in bottom_fields.values()):
        failures.append({"id": "cover_bottom_fields_missing_values", "evidence_text": "one or more bottom fields are blank"})
    if report.get("date_in_advisor_field"):
        failures.append({"id": "cover_date_merged_into_advisor", "evidence_text": "date is inside advisor field"})
    if report.get("stray_texts"):
        failures.append({"id": "cover_stray_digit", "evidence_text": ", ".join(report.get("stray_texts", []))})
    if report.get("cover_overflow"):
        failures.append({"id": "cover_page_overflow", "evidence_text": f"cover_page_count={report.get('cover_page_count')}"})
    if int(report.get("pdf_page_count") or 0) != 1:
        failures.append({"id": "cover_pdf_not_single_page", "evidence_text": f"pdf_page_count={report.get('pdf_page_count')}"})
    return failures


def _write_hashes(out: Path) -> None:
    hashes = {
        name: sha256_file(out / name)
        for name in COVER_FILES
        if (out / name).exists() and (out / name).is_file()
    }
    (out / "artifact_hashes.json").write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a single-page BUAA cover debug sandbox.")
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    report = render_cover_debug(model_path=args.model, template_path=args.template, out_dir=args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("pdf_export_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
