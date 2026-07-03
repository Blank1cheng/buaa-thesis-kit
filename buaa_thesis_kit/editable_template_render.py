from __future__ import annotations

import copy
import re
from dataclasses import replace
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

from buaa_thesis_kit.models import ContentBlock, Metadata, ThesisModel
from buaa_thesis_kit.template_fill import (
    _add_abstracts,
    _add_appendices,
    _add_equations,
    _add_figures,
    _add_references,
    _add_sections,
    _add_tables,
    _apply_conservative_formatting,
    finalize_equation_objects,
)


SPINE_MARKER = "书脊"
SAMPLE_BODY_START = "论文封面书脊"
PDF_EXTRACTED_TEXT_TITLE = "PDF Extracted Text"


def render_editable_buaa_docx(template_path: Path, model: ThesisModel, output_path: Path) -> None:
    """Render an editable BUAA thesis DOCX by reusing the official Word template."""
    document = Document(str(template_path))
    _apply_conservative_formatting(document, apply_page_setup=False)
    _replace_cover_fields(document, model.metadata)
    _compact_cover_spacing(document)
    _trim_template_after_cover(document)
    _append_spine_page(document, model.metadata)
    _append_model_content(document, model)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output))
    finalize_equation_objects(output, model.equations)


def _replace_cover_fields(document, metadata: Metadata) -> None:
    title = _metadata_value(metadata.title_cn or metadata.title_en or "Untitled Thesis")
    for paragraph in _cover_paragraphs(document):
        text = paragraph.text
        stripped = text.strip()
        if "单位代码" in text:
            _replace_paragraph_text_preserving_style(
                paragraph,
                f"                                                    单位代码       {_metadata_value(metadata.unit_code or '10006')}        ",
            )
        elif "学" in text and "号" in text and "学号" not in text:
            _replace_paragraph_text_preserving_style(
                paragraph,
                f"学    号     {_metadata_value(metadata.student_id)}       ",
            )
        elif "分类号" in text:
            _replace_paragraph_text_preserving_style(
                paragraph,
                f"分类号    {_metadata_value(metadata.classification)}         ",
            )
        elif stripped in {"（题目）", "(题目)"}:
            _replace_paragraph_text_preserving_style(paragraph, title)
        elif re.fullmatch(r"\d{4}年\d{1,2}月", stripped):
            _replace_paragraph_text_preserving_style(
                paragraph,
                _metadata_value(metadata.date),
            )

    if document.tables:
        _replace_cover_table(document.tables[0], metadata)


def _cover_paragraphs(document):
    for paragraph in document.paragraphs:
        if SAMPLE_BODY_START in paragraph.text:
            break
        yield paragraph


def _replace_cover_table(table, metadata: Metadata) -> None:
    values = {
        "学院名称": metadata.college,
        "专业名称": metadata.major,
        "学生姓名": metadata.student_name,
        "指导教师": metadata.advisor,
    }
    for row in table.rows:
        if len(row.cells) < 2:
            continue
        label = re.sub(r"\s+", "", row.cells[0].text)
        for key, value in values.items():
            if key in label:
                _replace_cell_text_preserving_style(
                    row.cells[1],
                    _metadata_value(value),
                    font_size=_cover_table_value_font_size(value),
                )
                break


def _trim_template_after_cover(document) -> None:
    body = document._body._element
    remove = False
    for child in list(body):
        if child.tag == qn("w:p") and SAMPLE_BODY_START in _xml_text(child):
            _remove_trailing_blank_paragraphs(body, child)
            remove = True
        if remove and child.tag != qn("w:sectPr"):
            body.remove(child)


def _compact_cover_spacing(document) -> None:
    body = document._body._element
    consecutive_blanks = 0
    for child in list(body):
        if child.tag == qn("w:p") and SAMPLE_BODY_START in _xml_text(child):
            break
        if child.tag == qn("w:p") and _is_removable_blank_paragraph(child):
            consecutive_blanks += 1
            if consecutive_blanks > 1:
                body.remove(child)
            continue
        consecutive_blanks = 0


def _remove_trailing_blank_paragraphs(body, marker) -> None:
    current = marker.getprevious()
    while current is not None and current.tag == qn("w:p") and _is_removable_blank_paragraph(current):
        previous = current.getprevious()
        body.remove(current)
        current = previous


def _is_removable_blank_paragraph(paragraph_element) -> bool:
    if _xml_text(paragraph_element).strip():
        return False
    protected_tags = {qn("w:drawing"), qn("w:pict")}
    return not any(node.tag in protected_tags for node in paragraph_element.iter())


def _append_spine_page(document, metadata: Metadata) -> None:
    document.add_page_break()
    marker = document.add_paragraph(SPINE_MARKER)
    marker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _format_runs(marker, bold=True, size=14)

    for value in _spine_values(metadata):
        paragraph = document.add_paragraph(value)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _format_runs(paragraph, size=12)


def _append_model_content(document, model: ThesisModel) -> None:
    document.add_page_break()
    _add_abstracts(document, model)
    _add_sections_with_page_breaks(document, _sections_without_pdf_placeholder_heading(model.sections))
    _add_tables(document, model.tables)
    _add_figures(document, model.figures)
    _add_equations(document, model.equations)
    _add_references(document, model.references)
    _add_appendices(document, model.appendices)


def _add_sections_with_page_breaks(document, sections: list[ContentBlock]) -> None:
    first = True
    for section in sections:
        if not first and _section_starts_new_page(section):
            document.add_page_break()
        _add_sections(document, [section])
        first = False


def _section_starts_new_page(section: ContentBlock) -> bool:
    title = _metadata_value(section.title)
    if title in {"本人声明", "摘要", "Abstract"}:
        return True
    return section.level <= 1 and bool(re.match(r"^\d+\s+\S+", title))


def _sections_without_pdf_placeholder_heading(sections: list[ContentBlock]) -> list[ContentBlock]:
    rendered: list[ContentBlock] = []
    for section in sections:
        if section.title == PDF_EXTRACTED_TEXT_TITLE:
            rendered.append(replace(section, title=""))
        else:
            rendered.append(section)
    return rendered


def _spine_values(metadata: Metadata) -> list[str]:
    return [
        value
        for value in [
            metadata.title_cn or metadata.title_en,
            metadata.student_name,
            metadata.college,
            metadata.major,
            metadata.date,
        ]
        if _metadata_value(value)
    ]


def _cover_table_value_font_size(value: str) -> float | None:
    length = len(_metadata_value(value))
    if length >= 16:
        return 10.5
    if length >= 10:
        return 12
    return None


def _replace_cell_text_preserving_style(
    cell,
    text: str,
    *,
    font_size: float | None = None,
) -> None:
    paragraph = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    _replace_paragraph_text_preserving_style(paragraph, text)
    if font_size is not None:
        _format_runs(paragraph, size=font_size)
    for extra in list(cell.paragraphs[1:]):
        extra._element.getparent().remove(extra._element)


def _replace_paragraph_text_preserving_style(paragraph, text: str) -> None:
    first_run_properties = None
    if paragraph.runs and paragraph.runs[0]._r.rPr is not None:
        first_run_properties = copy.deepcopy(paragraph.runs[0]._r.rPr)
    paragraph.clear()
    if not text:
        return
    run = paragraph.add_run(text)
    if first_run_properties is not None:
        run._r.insert(0, first_run_properties)


def _format_runs(paragraph, *, bold: bool = False, size: float = 12) -> None:
    for run in paragraph.runs:
        run.bold = bold
        run.font.size = Pt(size)


def _metadata_value(value: str) -> str:
    return str(value or "").strip()


def _xml_text(element) -> str:
    return "".join(node.text or "" for node in element.iter() if node.tag == qn("w:t"))


__all__ = ["render_editable_buaa_docx"]
