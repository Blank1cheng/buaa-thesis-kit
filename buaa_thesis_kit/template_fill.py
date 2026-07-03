from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.shared import Inches, Mm, Pt

from buaa_thesis_kit.models import AssetItem, ContentBlock, EquationItem, ThesisModel


PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z_]+)\s*\}\}")
BLOCK_PLACEHOLDERS = {"BODY", "REFERENCES", "TABLES", "FIGURES", "EQUATIONS", "APPENDICES"}
SUPPORTED_IMAGE_SUFFIXES = {".bmp", ".gif", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@dataclass(frozen=True)
class RenderedParagraph:
    text: str
    style: str | None = None
    alignment: WD_ALIGN_PARAGRAPH | None = None
    bold: bool = False


@dataclass(frozen=True)
class RenderedTable:
    block: ContentBlock


@dataclass(frozen=True)
class RenderedFigure:
    figure: AssetItem


def fill_word_template(template_path: Path, model: ThesisModel, output_path: Path) -> None:
    """Fill a DOCX template from a ThesisModel and save the authoritative Word file."""
    template_path = Path(template_path)
    output_path = Path(output_path)
    document = Document(str(template_path))

    has_placeholders = _document_has_placeholders(document)
    _apply_conservative_formatting(document, apply_page_setup=False)
    if has_placeholders:
        represented_placeholders = _represented_placeholders(document)
        _fill_placeholder_document(document, model)
        _remove_remaining_placeholders(document)
        _append_missing_content(document, model, represented_placeholders)
    else:
        _clear_body_preserving_sections(document)
        _apply_conservative_formatting(document, apply_page_setup=True)
        _build_fallback_document(document, model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output_path))


def _document_has_placeholders(document) -> bool:
    return any(PLACEHOLDER_RE.search(paragraph.text) for paragraph in _iter_all_paragraphs(document))


def _represented_placeholders(document) -> set[str]:
    represented: set[str] = set()
    for paragraph in _iter_all_paragraphs(document):
        for match in PLACEHOLDER_RE.finditer(paragraph.text):
            represented.add(match.group(1))
    return represented


def _fill_placeholder_document(document, model: ThesisModel) -> None:
    for paragraph in list(_iter_all_paragraphs(document)):
        if not PLACEHOLDER_RE.search(paragraph.text):
            continue
        if _has_block_placeholder(paragraph.text):
            rendered = _render_placeholder_items(paragraph.text, model)
            _replace_paragraph_with_items(paragraph, rendered)
        else:
            if not _replace_inline_placeholders_in_runs(paragraph, model):
                replacement = _replace_inline_placeholders(paragraph.text, model)
                _replace_paragraph_text(paragraph, _remove_unresolved_placeholders(replacement))


def _has_block_placeholder(text: str) -> bool:
    return any(match.group(1) in BLOCK_PLACEHOLDERS for match in PLACEHOLDER_RE.finditer(text))


def _render_placeholder_items(text: str, model: ThesisModel) -> list[RenderedParagraph | RenderedTable | RenderedFigure]:
    rendered: list[RenderedParagraph | RenderedTable | RenderedFigure] = []
    cursor = 0
    for match in PLACEHOLDER_RE.finditer(text):
        leading = text[cursor : match.start()]
        if leading:
            inline = _remove_unresolved_placeholders(_replace_inline_placeholders(leading, model))
            if inline:
                rendered.append(RenderedParagraph(inline))

        token = match.group(1)
        if token in BLOCK_PLACEHOLDERS:
            rendered.extend(_render_block_placeholder(token, model))
        else:
            inline = _remove_unresolved_placeholders(_scalar_placeholders(model).get(token, ""))
            if inline:
                rendered.append(RenderedParagraph(inline))
        cursor = match.end()

    trailing = text[cursor:]
    if trailing:
        inline = _remove_unresolved_placeholders(_replace_inline_placeholders(trailing, model))
        if inline:
            rendered.append(RenderedParagraph(inline))
    return rendered


def _render_block_placeholder(token: str, model: ThesisModel) -> list[RenderedParagraph | RenderedTable | RenderedFigure]:
    if token == "BODY":
        return _render_sections(model.sections)
    if token == "REFERENCES":
        return _render_references(model.references)
    if token == "TABLES":
        return [RenderedTable(table) for table in model.tables]
    if token == "FIGURES":
        return [RenderedFigure(figure) for figure in model.figures]
    if token == "EQUATIONS":
        return _render_equations(model.equations)
    if token == "APPENDICES":
        return _render_appendices(model.appendices)
    return []


def _replace_inline_placeholders(text: str, model: ThesisModel) -> str:
    values = _scalar_placeholders(model)

    def replace(match: re.Match[str]) -> str:
        return values.get(match.group(1), match.group(0))

    return PLACEHOLDER_RE.sub(replace, text)


def _replace_inline_placeholders_in_runs(paragraph: Paragraph, model: ThesisModel) -> bool:
    original_text = paragraph.text
    changed = False
    for run in paragraph.runs:
        if PLACEHOLDER_RE.search(run.text):
            run.text = _remove_unresolved_placeholders_preserving_spacing(
                _replace_inline_placeholders(run.text, model)
            )
            changed = True

    if not changed:
        return False
    if PLACEHOLDER_RE.search(paragraph.text):
        replacement = _replace_inline_placeholders(original_text, model)
        _replace_paragraph_text(paragraph, _remove_unresolved_placeholders(replacement))
        return False
    return True


def _scalar_placeholders(model: ThesisModel) -> dict[str, str]:
    metadata = model.metadata
    return {
        "TITLE_CN": metadata.title_cn,
        "TITLE_EN": metadata.title_en,
        "STUDENT_NAME": metadata.student_name,
        "STUDENT_ID": metadata.student_id,
        "COLLEGE": metadata.college,
        "MAJOR": metadata.major,
        "ADVISOR": metadata.advisor,
        "DATE": metadata.date,
        "CLASSIFICATION": metadata.classification,
        "UNIT_CODE": metadata.unit_code,
        "ABSTRACT_CN": _front_matter_value(
            model,
            "chinese_abstract",
            "abstract_cn",
            "cn_abstract",
        ),
        "ABSTRACT_EN": _front_matter_value(
            model,
            "english_abstract",
            "abstract_en",
            "en_abstract",
        ),
    }


def _front_matter_value(model: ThesisModel, *keys: str) -> str:
    for key in keys:
        value = model.front_matter.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(str(item) for item in value if item)
    return ""


def _remove_remaining_placeholders(document) -> None:
    for paragraph in _iter_all_paragraphs(document):
        if PLACEHOLDER_RE.search(paragraph.text):
            _replace_paragraph_text(paragraph, _remove_unresolved_placeholders(paragraph.text))


def _remove_unresolved_placeholders(text: str) -> str:
    text = PLACEHOLDER_RE.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _remove_unresolved_placeholders_preserving_spacing(text: str) -> str:
    return PLACEHOLDER_RE.sub("", text)


def _replace_paragraph_with_items(
    paragraph: Paragraph,
    rendered: list[RenderedParagraph | RenderedTable | RenderedFigure],
) -> None:
    if not rendered:
        _replace_paragraph_text(paragraph, "")
        return

    first = rendered[0]
    if isinstance(first, RenderedParagraph):
        _apply_rendered_paragraph(paragraph, first)
        anchor = paragraph._p
    else:
        _replace_paragraph_text(paragraph, "")
        anchor = _insert_item_after_anchor(paragraph, paragraph._p, first)

    for item in rendered[1:]:
        anchor = _insert_item_after_anchor(paragraph, anchor, item)


def _insert_paragraph_after(paragraph: Paragraph) -> Paragraph:
    new_element = OxmlElement("w:p")
    paragraph._p.addnext(new_element)
    return Paragraph(new_element, paragraph._parent)


def _insert_paragraph_after_anchor(paragraph: Paragraph, anchor) -> Paragraph:
    new_element = OxmlElement("w:p")
    anchor.addnext(new_element)
    return Paragraph(new_element, paragraph._parent)


def _insert_item_after_anchor(
    paragraph: Paragraph,
    anchor,
    item: RenderedParagraph | RenderedTable | RenderedFigure,
):
    if isinstance(item, RenderedParagraph):
        inserted = _insert_paragraph_after_anchor(paragraph, anchor)
        _apply_rendered_paragraph(inserted, item)
        return inserted._p
    if isinstance(item, RenderedTable):
        return _insert_table_after_anchor(paragraph, anchor, item.block)
    return _insert_figure_after_anchor(paragraph, anchor, item.figure)


def _insert_table_after_anchor(paragraph: Paragraph, anchor, table_block: ContentBlock):
    if table_block.title:
        title = _insert_paragraph_after_anchor(paragraph, anchor)
        _replace_paragraph_text(title, table_block.title)
        anchor = title._p

    rows = _parse_table_rows(table_block.text)
    if not rows:
        inserted = _insert_paragraph_after_anchor(paragraph, anchor)
        _replace_paragraph_text(inserted, table_block.text)
        return inserted._p

    column_count = max(len(row) for row in rows)
    try:
        table = paragraph._parent.add_table(rows=len(rows), cols=column_count, width=Inches(6))
    except TypeError:
        table = paragraph._parent.add_table(rows=len(rows), cols=column_count)
    _safe_set_table_style(table, "Table Grid")
    for row_index, row_values in enumerate(rows):
        for column_index in range(column_count):
            value = row_values[column_index] if column_index < len(row_values) else ""
            table.cell(row_index, column_index).text = value
    anchor.addnext(table._tbl)
    return table._tbl


def _insert_figure_after_anchor(paragraph: Paragraph, anchor, figure: AssetItem):
    image_path = Path(figure.path) if figure.path else None
    caption = _figure_caption(figure)
    if image_path and _is_supported_existing_image(image_path):
        picture = _insert_paragraph_after_anchor(paragraph, anchor)
        try:
            picture.add_run().add_picture(str(image_path), width=Inches(5.5))
            label = _insert_paragraph_after_anchor(paragraph, anchor)
            _replace_paragraph_text(label, f"[Figure inserted] {caption}".strip())
            return picture._p
        except Exception:
            _replace_paragraph_text(picture, _figure_review_text(figure))
            return picture._p

    review = _insert_paragraph_after_anchor(paragraph, anchor)
    _replace_paragraph_text(review, _figure_review_text(figure))
    return review._p


def _apply_rendered_paragraph(paragraph: Paragraph, rendered: RenderedParagraph) -> None:
    _replace_paragraph_text(paragraph, rendered.text)
    if rendered.style:
        _safe_set_style(paragraph, rendered.style)
    if rendered.alignment is not None:
        paragraph.alignment = rendered.alignment
    if rendered.bold:
        for run in paragraph.runs:
            run.bold = True


def _replace_paragraph_text(paragraph: Paragraph, text: str) -> None:
    paragraph.clear()
    if text:
        paragraph.add_run(text)


def _build_fallback_document(document, model: ThesisModel) -> None:
    _add_title_block(document, model)
    _add_abstracts(document, model)
    _add_sections(document, model.sections)
    _add_tables(document, model.tables)
    _add_figures(document, model.figures)
    _add_equations(document, model.equations)
    _add_references(document, model.references)
    _add_appendices(document, model.appendices)


def _append_missing_content(document, model: ThesisModel, represented_placeholders: set[str]) -> None:
    _append_missing_abstracts(document, model, represented_placeholders)
    for token in ("BODY", "TABLES", "FIGURES", "EQUATIONS", "REFERENCES", "APPENDICES"):
        if token in represented_placeholders:
            continue
        _append_block(document, token, model)


def _append_missing_abstracts(document, model: ThesisModel, represented_placeholders: set[str]) -> None:
    abstract_cn = _front_matter_value(model, "chinese_abstract", "abstract_cn", "cn_abstract")
    abstract_en = _front_matter_value(model, "english_abstract", "abstract_en", "en_abstract")
    if abstract_cn and "ABSTRACT_CN" not in represented_placeholders:
        _add_heading(document, "Chinese Abstract", level=1)
        _add_text_paragraphs(document, abstract_cn)
    if abstract_en and "ABSTRACT_EN" not in represented_placeholders:
        _add_heading(document, "English Abstract", level=1)
        _add_text_paragraphs(document, abstract_en)


def _append_block(document, token: str, model: ThesisModel) -> None:
    if token == "BODY":
        _add_sections(document, model.sections)
    elif token == "TABLES":
        _add_tables(document, model.tables)
    elif token == "FIGURES":
        _add_figures(document, model.figures)
    elif token == "EQUATIONS":
        _add_equations(document, model.equations)
    elif token == "REFERENCES":
        _add_references(document, model.references)
    elif token == "APPENDICES":
        _add_appendices(document, model.appendices)


def _add_title_block(document, model: ThesisModel) -> None:
    metadata = model.metadata
    title = metadata.title_cn or metadata.title_en or "Untitled Thesis"
    title_paragraph = document.add_paragraph()
    title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_paragraph.add_run(title)
    title_run.bold = True
    title_run.font.size = Pt(16)

    if metadata.title_en and metadata.title_en != title:
        english_title = document.add_paragraph()
        english_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = english_title.add_run(metadata.title_en)
        run.bold = True
        run.font.size = Pt(14)

    metadata_lines = [
        ("Student Name", metadata.student_name),
        ("Student ID", metadata.student_id),
        ("College", metadata.college),
        ("Major", metadata.major),
        ("Advisor", metadata.advisor),
        ("Date", metadata.date),
        ("Classification", metadata.classification),
        ("Unit Code", metadata.unit_code),
    ]
    for label, value in metadata_lines:
        if value:
            document.add_paragraph(f"{label}: {value}")


def _add_abstracts(document, model: ThesisModel) -> None:
    abstract_cn = _front_matter_value(model, "chinese_abstract", "abstract_cn", "cn_abstract")
    abstract_en = _front_matter_value(model, "english_abstract", "abstract_en", "en_abstract")
    if abstract_cn:
        _add_heading(document, "Chinese Abstract", level=1)
        _add_text_paragraphs(document, abstract_cn)
    if abstract_en:
        _add_heading(document, "English Abstract", level=1)
        _add_text_paragraphs(document, abstract_en)


def _add_sections(document, sections: Iterable[ContentBlock]) -> None:
    for item in _render_sections(sections):
        paragraph = document.add_paragraph()
        _apply_rendered_paragraph(paragraph, item)


def _add_tables(document, tables: Iterable[ContentBlock]) -> None:
    for table_block in tables:
        if table_block.title:
            document.add_paragraph(table_block.title)
        rows = _parse_table_rows(table_block.text)
        if not rows:
            if table_block.text:
                _add_text_paragraphs(document, table_block.text)
            continue
        column_count = max(len(row) for row in rows)
        table = document.add_table(rows=len(rows), cols=column_count)
        _safe_set_table_style(table, "Table Grid")
        for row_index, row_values in enumerate(rows):
            for column_index in range(column_count):
                value = row_values[column_index] if column_index < len(row_values) else ""
                table.cell(row_index, column_index).text = value


def _add_figures(document, figures: Iterable[AssetItem]) -> None:
    for figure in figures:
        image_path = Path(figure.path) if figure.path else None
        caption = _figure_caption(figure)
        if image_path and _is_supported_existing_image(image_path):
            picture = document.add_paragraph()
            try:
                picture.add_run().add_picture(str(image_path), width=Inches(5.5))
                document.add_paragraph(f"[Figure inserted] {caption}".strip())
            except Exception:
                _replace_paragraph_text(picture, _figure_review_text(figure))
        else:
            document.add_paragraph(_figure_review_text(figure))


def _add_equations(document, equations: Iterable[EquationItem]) -> None:
    for item in _render_equations(equations):
        document.add_paragraph(item.text)


def _add_references(document, references: Iterable[ContentBlock]) -> None:
    references = list(references)
    if not references:
        return
    _add_heading(document, "References", level=1)
    for item in _render_references(references):
        document.add_paragraph(item.text)


def _add_appendices(document, appendices: Iterable[ContentBlock]) -> None:
    for item in _render_appendices(appendices):
        paragraph = document.add_paragraph()
        _apply_rendered_paragraph(paragraph, item)


def _render_sections(sections: Iterable[ContentBlock]) -> list[RenderedParagraph]:
    rendered: list[RenderedParagraph] = []
    for section in sections:
        if section.title:
            rendered.append(RenderedParagraph(section.title, style=_heading_style(section.level)))
        rendered.extend(RenderedParagraph(text) for text in _split_paragraph_text(section.text))
    return rendered


def _render_references(references: Iterable[ContentBlock]) -> list[RenderedParagraph]:
    rendered: list[RenderedParagraph] = []
    for reference in references:
        text = reference.text or reference.title
        rendered.extend(RenderedParagraph(item) for item in _split_paragraph_text(text))
    return rendered


def _render_tables_as_paragraphs(tables: Iterable[ContentBlock]) -> list[RenderedParagraph]:
    rendered: list[RenderedParagraph] = []
    for table in tables:
        if table.title:
            rendered.append(RenderedParagraph(table.title))
        rows = _parse_table_rows(table.text)
        if rows:
            rendered.extend(RenderedParagraph(" | ".join(row)) for row in rows)
        else:
            rendered.extend(RenderedParagraph(text) for text in _split_paragraph_text(table.text))
    return rendered


def _render_figures_as_review_paragraphs(figures: Iterable[AssetItem]) -> list[RenderedParagraph]:
    return [RenderedParagraph(_figure_review_text(figure)) for figure in figures]


def _render_equations(equations: Iterable[EquationItem]) -> list[RenderedParagraph]:
    rendered: list[RenderedParagraph] = []
    for equation in equations:
        content = equation.latex or equation.text or "manual conversion required"
        number = f" {equation.number}" if equation.number else ""
        prefix = "[Equation requires review]" if equation.requires_review else "[Equation]"
        rendered.append(RenderedParagraph(f"{prefix}{number} {content}".strip()))
    return rendered


def _render_appendices(appendices: Iterable[ContentBlock]) -> list[RenderedParagraph]:
    rendered: list[RenderedParagraph] = []
    for appendix in appendices:
        if appendix.title:
            rendered.append(RenderedParagraph(appendix.title, style="Heading 1"))
        rendered.extend(RenderedParagraph(text) for text in _split_paragraph_text(appendix.text))
    return rendered


def _split_paragraph_text(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _parse_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        rows.append([cell.strip() for cell in line.split("\t")])
    return rows


def _figure_caption(figure: AssetItem) -> str:
    parts = [figure.caption, figure.path]
    return " ".join(part for part in parts if part)


def _figure_review_text(figure: AssetItem) -> str:
    return f"[Figure requires review] {_figure_caption(figure)}".strip()


def _is_supported_existing_image(path: Path) -> bool:
    return path.exists() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES


def _heading_style(level: int) -> str:
    return "Heading 1" if level <= 1 else "Heading 2"


def _add_heading(document, text: str, level: int = 1) -> None:
    paragraph = document.add_heading(text, level=level)
    if level == 1:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in paragraph.runs:
        run.bold = True


def _add_text_paragraphs(document, text: str) -> None:
    for paragraph_text in _split_paragraph_text(text):
        document.add_paragraph(paragraph_text)


def _safe_set_style(paragraph: Paragraph, style_name: str) -> None:
    try:
        paragraph.style = style_name
    except KeyError:
        return


def _safe_set_table_style(table, style_name: str) -> None:
    try:
        table.style = style_name
    except KeyError:
        return


def _iter_all_paragraphs(document) -> Iterable[Paragraph]:
    # Task 6 intentionally limits placeholder scanning to the document body.
    # Accessing missing header/footer objects through python-docx creates parts on save.
    for paragraph in document.paragraphs:
        yield paragraph
    for table in document.tables:
        yield from _iter_table_paragraphs(table)


def _iter_table_paragraphs(table) -> Iterable[Paragraph]:
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                yield paragraph
            for nested_table in cell.tables:
                yield from _iter_table_paragraphs(nested_table)


def _clear_body_preserving_sections(document) -> None:
    body = document._body._element
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _apply_conservative_formatting(document, *, apply_page_setup: bool) -> None:
    if apply_page_setup and len(document.sections) == 1:
        section = document.sections[0]
        section.page_width = Mm(210)
        section.page_height = Mm(297)
        section.top_margin = Mm(30)
        section.bottom_margin = Mm(25)
        section.left_margin = Mm(30)
        section.right_margin = Mm(20)

    try:
        normal = document.styles["Normal"]
    except KeyError:
        return

    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    rpr = normal._element.get_or_add_rPr()
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")
    rfonts.set(qn("w:eastAsia"), "SimSun")
