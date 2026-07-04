from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches

from buaa_thesis_kit.front_matter_renderer import render_front_matter
from buaa_thesis_kit.models import AssetItem, ContentBlock, ThesisModel
from buaa_thesis_kit.template_fill import (
    _add_appendices,
    _add_equations,
    _add_references,
    _add_sections,
    _add_tables,
    _apply_conservative_formatting,
    finalize_equation_objects,
)


PDF_EXTRACTED_TEXT_TITLE = "PDF Extracted Text"
SUPPORTED_INLINE_IMAGE_SUFFIXES = {".bmp", ".gif", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
FIGURE_MARKER_RE = re.compile(
    "^(?:(?:\u56fe)|fig(?:ure)?\\.?)\\s*(\\d+(?:[.\\-]\\d+)*)",
    flags=re.IGNORECASE,
)
FRONT_MATTER_SECTION_TITLES = {
    "本科毕业设计（论文）任务书",
    "本科毕业设计(论文)任务书",
    "毕业设计（论文）任务书",
    "毕业设计(论文)任务书",
    "任务书",
    "本人声明",
    "摘要",
    "Abstract",
    "目录",
}
COVER_METADATA_LABELS = (
    "学院",
    "院（系）名称",
    "专业",
    "专业名称",
    "学生姓名",
    "指导教师",
    "学号",
    "题目",
)
PDF_FRONT_MATTER_TITLE_PATTERNS = (
    r"^\d+\s*分类号$",
    r"^\d{4}\s*年\s*\d{1,2}\s*月$",
    r"^[ⅠⅡⅢⅣIVX]+、.*毕业设计.*",
    r"^[ⅠⅡⅢⅣIVX]+、.*主要参考资料",
)
PDF_FRONT_MATTER_TEXT_MARKERS = (
    "论文封面书脊",
    "毕业设计(论文)",
    "毕业设计（论文）题目",
    "本科毕业设计（论文）任务书",
    "四号黑体字",
)


def render_editable_buaa_docx(template_path: Path, model: ThesisModel, output_path: Path) -> None:
    """Render an editable BUAA thesis DOCX by reusing the official Word template."""
    document = Document(str(template_path))
    _apply_conservative_formatting(document, apply_page_setup=False)
    body_sections = _body_sections(model.sections)
    render_front_matter(document, model, body_sections)
    _append_model_content(document, model, body_sections)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output))
    finalize_equation_objects(output, model.equations)


def _append_model_content(document, model: ThesisModel, body_sections: list[ContentBlock]) -> None:
    _add_sections_with_page_breaks(
        document,
        body_sections,
        model.figures,
    )
    _add_tables(document, model.tables)
    _add_equations(document, _trusted_editable_equations(model))
    _add_references(document, model.references)
    _add_appendices(document, model.appendices)


def _trusted_editable_equations(model: ThesisModel):
    return [
        equation
        for equation in model.equations
        if equation.omml.strip()
    ]


def _body_sections(sections: list[ContentBlock]) -> list[ContentBlock]:
    return [
        section
        for section in _sections_without_pdf_placeholder_heading(sections)
        if not _is_front_matter_section(section)
    ]


def _is_front_matter_section(section: ContentBlock) -> bool:
    title = _metadata_value(section.title)
    compact_title = re.sub(r"\s+", "", title)
    if compact_title in {re.sub(r"\s+", "", item) for item in FRONT_MATTER_SECTION_TITLES}:
        return True
    if any(re.match(pattern, title) for pattern in PDF_FRONT_MATTER_TITLE_PATTERNS):
        return True
    lines = [line.strip() for line in str(section.text or "").splitlines() if line.strip()]
    joined_text = "\n".join(lines)
    if any(marker in title or marker in joined_text for marker in PDF_FRONT_MATTER_TEXT_MARKERS):
        return True
    if not title and 1 <= len(lines) <= 10:
        hit_count = sum(1 for line in lines if any(label in line for label in COVER_METADATA_LABELS))
        return hit_count >= 2
    if lines:
        hit_count = sum(1 for line in lines if any(label in line for label in COVER_METADATA_LABELS))
        if hit_count >= 3 and not re.match(r"^\d+(?:\.\d+)*\s+\S+", title):
            return True
    return False


def _add_sections_with_page_breaks(
    document,
    sections: list[ContentBlock],
    figures: list[AssetItem] | None = None,
) -> set[str]:
    rendered_figure_ids: set[str] = set()
    first = True
    for section in sections:
        if not first and _section_starts_new_page(section):
            document.add_page_break()
        _add_section_with_inline_figures(document, section, figures or [], rendered_figure_ids)
        first = False
    return rendered_figure_ids


def _add_section_with_inline_figures(
    document,
    section: ContentBlock,
    figures: list[AssetItem],
    rendered_figure_ids: set[str],
) -> None:
    if section.title:
        _add_sections(document, [replace(section, text="")])
    for text in _split_section_text(section.text):
        figure = _matching_captioned_figure(text, figures, rendered_figure_ids)
        if figure is not None and _add_inline_figure(document, figure):
            rendered_figure_ids.add(figure.id)
        document.add_paragraph(text)


def _matching_captioned_figure(
    paragraph_text: str,
    figures: list[AssetItem],
    rendered_figure_ids: set[str],
) -> AssetItem | None:
    paragraph_key = _caption_key(paragraph_text)
    if not paragraph_key:
        return None
    paragraph_marker = _figure_marker_key(paragraph_text)
    for figure in figures:
        if figure.id in rendered_figure_ids:
            continue
        if _caption_key(figure.caption) == paragraph_key:
            return figure
        if paragraph_marker and _figure_marker_key(figure.caption) == paragraph_marker:
            return figure
    return None


def _add_inline_figure(document, figure: AssetItem) -> bool:
    image_path = Path(figure.path) if figure.path else None
    if image_path is None or not _is_supported_inline_image(image_path):
        return False
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    try:
        paragraph.add_run().add_picture(str(image_path), width=Inches(5.5))
    except Exception:
        parent = paragraph._element.getparent()
        if parent is not None:
            parent.remove(paragraph._element)
        return False
    return True


def _is_supported_inline_image(path: Path) -> bool:
    return path.exists() and path.is_file() and path.suffix.lower() in SUPPORTED_INLINE_IMAGE_SUFFIXES


def _split_section_text(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _caption_key(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).casefold()


def _figure_marker_key(text: str) -> str:
    match = FIGURE_MARKER_RE.match(str(text or "").strip())
    if not match:
        return ""
    return match.group(1).replace("-", ".").casefold()


def _section_starts_new_page(section: ContentBlock) -> bool:
    title = _metadata_value(section.title)
    if title in {"本人声明", "摘要", "Abstract"}:
        return True
    return section.level <= 1 and bool(
        re.match(r"^\d+\s+\S+", title)
        or re.match(r"^第[一二三四五六七八九十百]+章\s+\S+$", title)
    )


def _sections_without_pdf_placeholder_heading(sections: list[ContentBlock]) -> list[ContentBlock]:
    rendered: list[ContentBlock] = []
    for section in sections:
        if section.title == PDF_EXTRACTED_TEXT_TITLE:
            rendered.append(replace(section, title=""))
        else:
            rendered.append(section)
    return rendered


def _metadata_value(value: str) -> str:
    return str(value or "").strip()


__all__ = ["render_editable_buaa_docx"]
