from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree

from buaa_thesis_kit.models import (
    AssetItem,
    ContentBlock,
    EquationItem,
    Metadata,
    SourceEvidence,
    ThesisModel,
)


SOURCE_DOCX_NAME = "source.docx"
MAX_MEDIA_BYTES = 25 * 1024 * 1024
MAX_TOTAL_MEDIA_BYTES = 100 * 1024 * 1024
CONFLICT_CHECK_FIELDS = {
    "title_cn",
    "title_en",
    "student_name",
    "student_id",
    "college",
    "major",
    "advisor",
    "date",
    "classification",
    "unit_code",
}
COVER_COMPACT_LABELS: dict[str, tuple[str, ...]] = {
    "student_id": ("学生学号", "学号"),
    "unit_code": ("单位代码", "学校代码"),
    "classification": ("中图分类号", "分类号"),
}
COVER_DATE_RE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?")


@dataclass(frozen=True)
class TextBlock:
    index: int
    kind: str
    text: str
    style_name: str = ""
    table_index: int | None = None
    row_index: int | None = None
    cell_index: int | None = None


@dataclass(frozen=True)
class ScanUnit:
    text: str
    block: TextBlock | None
    method: str
    confidence: float


FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "title_cn": (
        r"中文题目",
        r"中文题名",
        r"论文题目",
        r"论文题名",
        r"毕业设计\s*[（(]\s*论文\s*[）)]\s*题目",
        r"题目",
    ),
    "title_en": (
        r"英文题目",
        r"英文题名",
        r"English\s+Title",
        r"Title\s+in\s+English",
    ),
    "student_name": (r"学生姓名", r"作者姓名", r"作者", r"姓名", r"Name"),
    "student_id": (r"学生学号", r"学号", r"Student\s*(?:ID|No\.?|Number)"),
    "college": (r"所在学院", r"学院", r"院系", r"College", r"School"),
    "major": (r"专业名称", r"专业", r"Major"),
    "advisor": (r"指导教师姓名", r"指导教师", r"导师姓名", r"导师", r"Advisor", r"Supervisor"),
    "date": (r"完成日期", r"提交日期", r"日期", r"Date"),
    "classification": (r"中图分类号", r"分类号", r"Classification"),
    "unit_code": (r"单位代码", r"学校代码", r"Unit\s+Code", r"Institution\s+Code"),
}

def _labels_by_specificity(labels: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(labels, key=len, reverse=True))


SORTED_FIELD_LABELS = {
    field: _labels_by_specificity(labels) for field, labels in FIELD_LABELS.items()
}

ALL_LABEL_RE = re.compile(
    "|".join(_labels_by_specificity(label for labels in FIELD_LABELS.values() for label in labels)),
    re.IGNORECASE,
)

SEPARATOR_CHARS = ":：;；,，|/\t "


def extract_thesis_model(docx_path: Path, work_dir: Path) -> ThesisModel:
    """Extract a Phase 1 thesis model from a DOCX document."""
    docx_path = Path(docx_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    model = ThesisModel()
    if docx_path.suffix.lower() != ".docx":
        model.extraction_warnings.append(f"unreadable or non-DOCX input: {docx_path}")
        model.status = "failed"
        return model

    source_copy = work_dir / SOURCE_DOCX_NAME
    try:
        if docx_path.resolve() != source_copy.resolve():
            shutil.copy2(docx_path, source_copy)
    except OSError as exc:
        model.extraction_warnings.append(f"unable to copy source DOCX: {exc}")
        model.status = "failed"
        return model

    try:
        document = Document(str(source_copy))
    except Exception as exc:  # python-docx raises several XML/ZIP errors.
        model.extraction_warnings.append(f"unreadable DOCX: {exc}")
        model.status = "failed"
        return model

    text_blocks, model.tables = _read_text_blocks_and_tables(document)
    model.figures, media_warnings = _extract_media(source_copy, work_dir)
    model.equations = _extract_equations(source_copy)

    if not text_blocks:
        model.extraction_warnings.append("no body content found")
        model.status = "failed"
        return model

    model.metadata, metadata_warnings = _extract_metadata(text_blocks)
    front_matter, sections, references, appendices = _split_content(text_blocks)
    model.front_matter = front_matter
    model.sections = sections
    model.references = references
    model.appendices = appendices
    model.extraction_warnings.extend(metadata_warnings)
    model.extraction_warnings.extend(media_warnings)
    model.extraction_warnings.extend(_build_warnings(model))

    has_review_items = any(item.requires_review for item in model.figures) or any(
        item.requires_review for item in model.equations
    )
    model.status = "needs_review" if model.extraction_warnings or has_review_items else "draft"
    return model


def _read_text_blocks_and_tables(document) -> tuple[list[TextBlock], list[ContentBlock]]:
    blocks: list[TextBlock] = []
    tables: list[ContentBlock] = []
    block_index = 0
    table_index = 0

    for item in _iter_body_items(document):
        if isinstance(item, Paragraph):
            text = _clean_text(item.text)
            if text:
                blocks.append(
                    TextBlock(
                        index=block_index,
                        kind="paragraph",
                        text=text,
                        style_name=item.style.name if item.style else "",
                    )
                )
                block_index += 1
        elif isinstance(item, Table):
            table_index += 1
            rows: list[list[str]] = []
            first_block_index = block_index
            for row_idx, row in enumerate(item.rows):
                row_values: list[str] = []
                for cell_idx, cell in enumerate(row.cells):
                    text = _clean_text(cell.text)
                    row_values.append(text)
                    if text:
                        blocks.append(
                            TextBlock(
                                index=block_index,
                                kind="table_cell",
                                text=text,
                                table_index=table_index,
                                row_index=row_idx,
                                cell_index=cell_idx,
                            )
                        )
                        block_index += 1
                rows.append(row_values)
            table_text = "\n".join("\t".join(cell for cell in row if cell) for row in rows).strip()
            if table_text:
                tables.append(
                    ContentBlock(
                        id=f"tbl-{len(tables) + 1}",
                        type="table",
                        text=table_text,
                        source=_source("docx-table", first_block_index, 0.8, False),
                    )
                )
    return blocks, tables


def _iter_body_items(document) -> Iterable[Paragraph | Table]:
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def _extract_metadata(blocks: list[TextBlock]) -> tuple[Metadata, list[str]]:
    metadata = Metadata()
    warnings: list[str] = []
    units = _metadata_scan_units(blocks[:100])

    for field in FIELD_LABELS:
        chosen_value = ""
        chosen_unit: ScanUnit | None = None
        conflict_reported = False
        for unit in units:
            value = _extract_value_for_field(field, unit.text)
            if not value:
                continue
            if not chosen_value:
                chosen_value = value
                chosen_unit = unit
                continue
            if (
                field in CONFLICT_CHECK_FIELDS
                and _metadata_value_key(value) != _metadata_value_key(chosen_value)
                and not conflict_reported
            ):
                warnings.append(f"conflicting metadata field: {field}")
                conflict_reported = True
        if chosen_value and chosen_unit is not None:
            setattr(metadata, field, chosen_value)
            metadata.evidence[field] = _source(
                chosen_unit.method,
                chosen_unit.block.index if chosen_unit.block else None,
                chosen_unit.confidence,
                False,
            )

    if not metadata.title_cn:
        title, block = _guess_chinese_title(blocks[:30])
        if title:
            metadata.title_cn = title
            metadata.evidence["title_cn"] = _source(
                "metadata-title-heuristic",
                block.index,
                0.45,
                True,
            )

    if not metadata.date:
        date, block = _guess_cover_date(blocks[:30])
        if date and block is not None:
            metadata.date = date
            metadata.evidence["date"] = _source(
                "metadata-cover-date-heuristic",
                block.index,
                0.58,
                True,
            )

    if "unit_code" not in metadata.evidence:
        metadata.unit_code = "10006"
        metadata.evidence["unit_code"] = _source("metadata-default", None, 0.6, False)

    return metadata, warnings


def _metadata_value_key(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _metadata_scan_units(blocks: list[TextBlock]) -> list[ScanUnit]:
    units = [
        ScanUnit(block.text, block, _metadata_method(block), 0.9 if block.kind == "paragraph" else 0.82)
        for block in blocks
    ]

    table_rows: dict[tuple[int, int], list[TextBlock]] = {}
    for block in blocks:
        if block.table_index is None or block.row_index is None:
            continue
        table_rows.setdefault((block.table_index, block.row_index), []).append(block)

    for row_blocks in table_rows.values():
        row_blocks.sort(key=lambda item: item.cell_index or 0)
        row_text = " ".join(block.text for block in row_blocks if block.text)
        if row_text:
            units.append(ScanUnit(row_text, row_blocks[0], "metadata-table-row", 0.92))

    return units


def _metadata_method(block: TextBlock) -> str:
    return "metadata-table-cell" if block.kind == "table_cell" else "metadata-paragraph"


def _extract_value_for_field(field: str, text: str) -> str:
    labels = SORTED_FIELD_LABELS[field]
    match = re.search("|".join(labels), text, flags=re.IGNORECASE)
    if not match:
        compact_value = _extract_compact_cover_value(field, text)
        if compact_value:
            return compact_value
        return ""

    if field == "title_cn" and _is_english_title_label(text, match):
        return ""

    tail = text[match.end() :]
    tail = re.sub(r"^[\s:：;；,，\-—_（）()\[\]【】]+", "", tail)
    if not tail:
        return ""
    next_label_start = _next_label_start(tail)
    if next_label_start is not None and next_label_start > 0:
        tail = tail[:next_label_start]
    return _clean_metadata_value(field, tail)


def _is_english_title_label(text: str, match: re.Match[str]) -> bool:
    prefix = text[max(0, match.start() - 8) : match.start()]
    return "英文" in prefix or "English" in prefix


def _next_label_start(text: str) -> int | None:
    for match in ALL_LABEL_RE.finditer(text):
        start = match.start()
        end = match.end()
        before_ok = start == 0 or text[start - 1].isspace() or text[start - 1] in SEPARATOR_CHARS
        after_ok = end == len(text) or text[end].isspace() or text[end] in SEPARATOR_CHARS
        if before_ok and after_ok:
            return start
    return None


def _clean_metadata_value(field: str, value: str) -> str:
    value = _clean_text(value).strip(" :：;；,，。.-—_[]【】（）()")
    if field == "student_id":
        match = re.search(r"\d{8,10}", value)
        return match.group(0) if match else ""
    if field == "unit_code":
        match = re.search(r"\d{5}", value)
        return match.group(0) if match else ""
    if field == "date":
        match = re.search(r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?", value)
        if match:
            return re.sub(r"\s+", "", match.group(0))
    if field == "title_cn" and not _contains_cjk(value):
        return ""
    if field == "title_en" and not re.search(r"[A-Za-z]", value):
        return ""
    return value


def _extract_compact_cover_value(field: str, text: str) -> str:
    labels = COVER_COMPACT_LABELS.get(field)
    if not labels:
        return ""
    compact_text = re.sub(r"\s+", "", text)
    for label in labels:
        if label not in compact_text:
            continue
        tail = compact_text.split(label, 1)[1]
        return _clean_metadata_value(field, tail)
    return ""


def _guess_cover_date(blocks: list[TextBlock]) -> tuple[str, TextBlock] | tuple[str, None]:
    for block in blocks:
        text = block.text
        if _contains_any_label(text):
            continue
        match = COVER_DATE_RE.search(text)
        if match:
            return re.sub(r"\s+", "", match.group(0)), block
    return "", None


def _guess_chinese_title(blocks: list[TextBlock]) -> tuple[str, TextBlock] | tuple[str, None]:
    for block in blocks:
        text = block.text
        if not (4 <= len(text) <= 80):
            continue
        if not _contains_cjk(text) or _contains_any_label(text):
            continue
        if _is_structural_marker(text) or re.search(r"\d{8,10}", text):
            continue
        return text, block
    return "", None


def _split_content(
    blocks: list[TextBlock],
) -> tuple[dict[str, str], list[ContentBlock], list[ContentBlock], list[ContentBlock]]:
    front_matter_lines: dict[str, list[str]] = {}
    sections: list[ContentBlock] = []
    references: list[ContentBlock] = []
    appendices: list[ContentBlock] = []
    current: ContentBlock | None = None
    mode: str | None = None

    for block in blocks:
        text = block.text
        if block.kind == "table_cell":
            continue
        if _is_toc_heading(text):
            mode = "toc"
            current = None
            continue
        if _is_chinese_abstract_heading(text):
            mode = "chinese_abstract"
            current = None
            _append_inline_after_heading(front_matter_lines, "chinese_abstract", text)
            continue
        if _is_english_abstract_heading(text):
            mode = "english_abstract"
            current = None
            _append_inline_after_heading(front_matter_lines, "english_abstract", text)
            continue
        if _is_references_heading(text):
            mode = "references"
            current = None
            continue
        if _is_appendix_heading(text):
            block_item = ContentBlock(
                id=f"app-{len(appendices) + 1}",
                type="appendix",
                title=text,
                level=1,
                source=_source("docx-heading", block.index, 0.86, False),
            )
            appendices.append(block_item)
            current = block_item
            mode = "appendix"
            continue
        if _is_acknowledgement_heading(text):
            block_item = ContentBlock(
                id=f"sec-{len(sections) + 1}",
                type="acknowledgements",
                title=text,
                level=1,
                source=_source("docx-heading", block.index, 0.84, False),
            )
            sections.append(block_item)
            current = block_item
            mode = "acknowledgements"
            continue

        if mode == "toc":
            if _looks_like_toc_entry(text, allow_plain_page_number=True) or _is_structural_marker(text):
                continue
            mode = None

        if mode in {"chinese_abstract", "english_abstract"}:
            if _is_keywords_line(text):
                continue
            heading = _detect_heading(block)
            if heading is None:
                front_matter_lines.setdefault(mode, []).append(text)
                continue
            mode = None

        if mode == "references":
            if _is_reference_entry(text) or _detect_heading(block) is None:
                references.append(
                    ContentBlock(
                        id=f"ref-{len(references) + 1}",
                        type="reference",
                        text=text,
                        source=_source("docx-reference", block.index, 0.86, False),
                    )
                )
                continue

        heading = _detect_heading(block)
        if heading is not None:
            title, level, confidence = heading
            block_item = ContentBlock(
                id=f"sec-{len(sections) + 1}",
                type="chapter" if level == 1 else "section",
                title=title,
                level=level,
                source=_source("docx-heading", block.index, confidence, False),
            )
            sections.append(block_item)
            current = block_item
            mode = "body"
            continue

        if current is not None and mode in {"body", "acknowledgements", "appendix"}:
            current.text = _append_text(current.text, text)

    front_matter = {key: "\n".join(value).strip() for key, value in front_matter_lines.items() if value}
    return front_matter, sections, references, appendices


def _append_inline_after_heading(lines: dict[str, list[str]], key: str, text: str) -> None:
    inline = re.sub(
        r"^(?:中文摘要|摘要|英文摘要|ABSTRACT|Abstract)\s*[:：]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    if inline and inline != text:
        lines.setdefault(key, []).append(inline)
    else:
        lines.setdefault(key, [])


def _detect_heading(block: TextBlock) -> tuple[str, int, float] | None:
    text = block.text
    if _looks_like_toc_entry(text) or _is_structural_marker(text):
        return None

    style = block.style_name.lower()
    if style.startswith("heading") or style.startswith("标题"):
        level_match = re.search(r"(\d+)", block.style_name)
        level = int(level_match.group(1)) if level_match else 1
        return text, max(1, level), 0.95

    if re.match(r"^第[一二三四五六七八九十百零〇两]+章\s+\S+", text):
        return text, 1, 0.88
    numbered = re.match(r"^(\d+(?:\.\d+){1,4})\s+\S+", text)
    if numbered:
        return text, numbered.group(1).count(".") + 1, 0.86
    if re.match(r"^\d+\s+[\u4e00-\u9fffA-Za-z].{0,60}$", text) and not re.match(r"^\d{4}\s*年", text):
        return text, 1, 0.78
    return None


def _extract_media(source_copy: Path, work_dir: Path) -> tuple[list[AssetItem], list[str]]:
    figures: list[AssetItem] = []
    warnings: list[str] = []
    image_dir = work_dir / "image"
    used_names: set[str] = set()
    total_media_bytes = 0
    try:
        with zipfile.ZipFile(source_copy) as docx_zip:
            media_infos = [
                info
                for info in docx_zip.infolist()
                if info.filename.startswith("word/media/") and not info.filename.endswith("/")
            ]
            for info in media_infos:
                if info.file_size > MAX_MEDIA_BYTES:
                    warnings.append(f"skipped oversized media: {Path(info.filename).name}")
                    continue
                if total_media_bytes + info.file_size > MAX_TOTAL_MEDIA_BYTES:
                    warnings.append(f"skipped media after total size limit: {Path(info.filename).name}")
                    continue
                image_dir.mkdir(parents=True, exist_ok=True)
                destination = _unique_media_destination(image_dir, Path(info.filename).name, used_names)
                destination.write_bytes(docx_zip.read(info))
                total_media_bytes += info.file_size
                figures.append(
                    AssetItem(
                        id=f"img-{len(figures) + 1}",
                        type="image",
                        path=str(destination.resolve()),
                        source=_source("docx-media", None, 0.88, True),
                        requires_review=True,
                    )
                )
    except zipfile.BadZipFile:
        return figures, warnings
    return figures, warnings


def _unique_media_destination(image_dir: Path, original_name: str, used_names: set[str]) -> Path:
    safe_name = _safe_media_basename(original_name)
    path = Path(safe_name)
    stem = path.stem or "media"
    suffix = path.suffix
    candidate = safe_name
    counter = 2
    while candidate in used_names or (image_dir / candidate).exists():
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(candidate)
    return image_dir / candidate


def _safe_media_basename(original_name: str) -> str:
    basename = Path(original_name).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", basename).strip("._")
    return safe_name or "media.bin"


def _extract_equations(source_copy: Path) -> list[EquationItem]:
    equations: list[EquationItem] = []
    try:
        with zipfile.ZipFile(source_copy) as docx_zip:
            if "word/document.xml" in docx_zip.namelist():
                equations.extend(_extract_omml_equations(docx_zip.read("word/document.xml")))
            embedding_names = [
                name
                for name in docx_zip.namelist()
                if name.startswith("word/embeddings/") and not name.endswith("/")
            ]
            for name in embedding_names:
                equations.append(
                    EquationItem(
                        id=f"eq-{len(equations) + 1}",
                        kind="embedded-object",
                        text=Path(name).name,
                        source=_source("docx-embedding", None, 0.72, True),
                        requires_review=True,
                    )
                )
    except zipfile.BadZipFile:
        return equations
    return equations


def _extract_omml_equations(document_xml: bytes) -> list[EquationItem]:
    try:
        root = etree.fromstring(document_xml)
    except etree.XMLSyntaxError:
        return []

    omml_nodes = root.xpath("//*[local-name()='oMathPara']")
    omml_nodes.extend(root.xpath("//*[local-name()='oMath' and not(ancestor::*[local-name()='oMathPara'])]"))
    equations: list[EquationItem] = []
    for node in omml_nodes:
        text = "".join(node.xpath(".//*[local-name()='t']/text()")).strip()
        review_required = True
        equations.append(
            EquationItem(
                id=f"eq-{len(equations) + 1}",
                kind="omml",
                text=text,
                source=_source("docx-omml", None, 0.95, review_required),
                requires_review=review_required,
            )
        )
    return equations


def _build_warnings(model: ThesisModel) -> list[str]:
    warnings: list[str] = []
    for field in ("title_cn", "student_name", "student_id", "college", "major", "advisor", "date"):
        if not getattr(model.metadata, field):
            warnings.append(f"missing metadata field: {field}")

    title_evidence = model.metadata.evidence.get("title_cn")
    if model.metadata.title_cn and title_evidence and title_evidence.confidence < 0.7:
        warnings.append("low-confidence title_cn")
    if any(equation.kind == "omml" and equation.requires_review for equation in model.equations):
        warnings.append("OMML equations require TeX review")
    if "chinese_abstract" not in model.front_matter:
        warnings.append("missing chinese abstract")
    if "english_abstract" not in model.front_matter:
        warnings.append("missing english abstract")
    if not model.sections:
        warnings.append("missing body sections")
    if not model.references:
        warnings.append("missing references")
    return warnings


def _source(
    method: str,
    paragraph_index: int | None,
    confidence: float,
    requires_review: bool,
) -> SourceEvidence:
    return SourceEvidence(
        file=SOURCE_DOCX_NAME,
        method=method,
        paragraph_index=paragraph_index,
        confidence=confidence,
        requires_review=requires_review,
    )


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def _append_text(existing: str, text: str) -> str:
    return f"{existing}\n{text}".strip() if existing else text


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _contains_any_label(text: str) -> bool:
    return bool(ALL_LABEL_RE.search(text))


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


def _is_structural_marker(text: str) -> bool:
    compact = _compact(text).lower()
    return compact in {
        "封面",
        "任务书",
        "原创性声明",
        "目录",
        "contents",
        "摘要",
        "中文摘要",
        "abstract",
        "英文摘要",
        "关键词",
        "keywords",
    }


def _is_toc_heading(text: str) -> bool:
    compact = _compact(text).lower()
    return compact in {"目录", "contents"}


def _looks_like_toc_entry(text: str, allow_plain_page_number: bool = False) -> bool:
    if re.search(r"(?:\.{2,}|…{2,}|·{2,})\s*\d+\s*$", text):
        return True
    if not allow_plain_page_number:
        return False
    if re.match(r"^\d+(?:\.\d+)*\s+\S.*\s+\d+$", text):
        return True
    return bool(re.match(r"^第[一二三四五六七八九十百零〇两]+章\s+\S.*\s+\d+$", text))


def _is_chinese_abstract_heading(text: str) -> bool:
    compact = _compact(text)
    return compact in {"摘要", "中文摘要"} or bool(re.match(r"^(?:中文摘要|摘要)\s*[:：]\s*\S+", text))


def _is_english_abstract_heading(text: str) -> bool:
    compact = _compact(text).lower()
    return compact in {"abstract", "英文摘要"} or bool(
        re.match(r"^(?:ABSTRACT|Abstract|英文摘要)\s*[:：]\s*\S+", text)
    )


def _is_keywords_line(text: str) -> bool:
    return bool(re.match(r"^(?:关键词|关键字|Keywords?)\s*[:：]", text, flags=re.IGNORECASE))


def _is_references_heading(text: str) -> bool:
    compact = _compact(text).lower()
    return compact in {"参考文献", "references", "bibliography"}


def _is_reference_entry(text: str) -> bool:
    return bool(re.match(r"^\[\d+\]", text))


def _is_appendix_heading(text: str) -> bool:
    return bool(re.match(r"^附录(?:\s*[A-ZＡ-Ｚ一二三四五六七八九十])?", text, flags=re.IGNORECASE))


def _is_acknowledgement_heading(text: str) -> bool:
    compact = _compact(text).lower()
    return compact in {"致谢", "致謝", "acknowledgements", "acknowledgments"}
