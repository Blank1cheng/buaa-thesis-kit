from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from buaa_thesis_kit.models import AssetItem, ContentBlock, Metadata, SourceEvidence, ThesisModel


SOURCE_PDF_NAME = "source.pdf"


@dataclass(frozen=True)
class PdfLine:
    index: int
    page: int
    text: str


@dataclass(frozen=True)
class PdfTextBlock:
    bbox: tuple[float, float, float, float]
    text: str


@dataclass(frozen=True)
class PdfImageCandidate:
    index: int
    page: int
    bbox: tuple[float, float, float, float]
    caption: str


FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "title_cn": ("中文题目", "论文题目", "毕业设计（论文）题目", "题目"),
    "title_en": ("English Title", "Title in English", "Title"),
    "student_name": ("学生姓名", "作者姓名", "Student Name", "Author", "Name"),
    "student_id": ("学生学号", "学号", "Student ID", "Student No", "Student Number"),
    "college": ("学院名称", "所在学院", "学院", "College", "School"),
    "major": ("专业名称", "专业", "Major"),
    "advisor": ("指导教师姓名", "指导教师", "导师", "Advisor", "Supervisor"),
    "date": ("完成日期", "提交日期", "日期", "Date"),
    "classification": ("中图分类号", "分类号", "Classification"),
    "unit_code": ("单位代码", "学校代码", "Unit Code", "Institution Code"),
}
REQUIRED_METADATA = ("title_cn", "student_name", "student_id", "college", "major", "advisor", "date")
REFERENCE_HEADINGS = {"references", "reference", "参考文献"}
TOC_HEADINGS = {"目录", "目 录", "contents", "table of contents"}
SPLIT_HEADING_PAIRS = {
    ("摘", "要"): "摘要",
    ("目", "录"): "目录",
}
FRONT_MATTER_HEADINGS = {"本人声明", "摘要", "Abstract"}
RUNNING_HEADER_PREFIXES = (
    "北京航空航天大学毕业设计(论文)",
    "北京航空航天大学毕业设计（论文）",
)
PAGE_NUMBER_MARKERS = {"第", "页"}
FIGURE_CAPTION_RE = re.compile(
    "^(?:(?:\u56fe)\\s*\\d+(?:[.\\-]\\d+)*|fig(?:ure)?\\.?\\s*\\d+(?:[.\\-]\\d+)*)\\s+.+",
    flags=re.IGNORECASE,
)
TABLE_CAPTION_RE = re.compile(
    "^(?:(?:\u8868)\\s*\\d+(?:[.\\-]\\d+)*|table\\s+\\d+(?:[.\\-]\\d+)*)\\s+.+",
    flags=re.IGNORECASE,
)
MIN_DISPLAY_IMAGE_AREA = 5_000.0
LARGE_UNCAPTIONED_IMAGE_AREA = 40_000.0
MAX_FIGURE_CAPTION_DISTANCE = 90.0
NEXT_LINE_LABELS: dict[str, str] = {
    "单位代码": "unit_code",
    "学校代码": "unit_code",
    "分类号": "classification",
    "1分类号": "classification",
    "1 分类号": "classification",
    "中图分类号": "classification",
}
VERTICAL_FIELD_LABELS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("学", "号"), "student_id"),
    (("学", "院", "名", "称"), "college"),
    (("专", "业", "名", "称"), "major"),
    (("学", "生", "姓", "名"), "student_name"),
    (("指", "导", "教", "师"), "advisor"),
)
TITLE_ANCHORS = {"毕业设计(论文)", "毕业设计（论文）", "本科毕业设计(论文)", "本科毕业设计（论文）"}
BUAA_SPINE_MARKER = "论文封面书脊"
BUAA_TASK_BOOK_TITLE = "本科生毕业设计（论文）任务书"


def extract_pdf_model(pdf_path: Path, work_dir: Path) -> ThesisModel:
    """Extract a reviewable ThesisModel from a PDF source."""
    source = Path(pdf_path)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    model = ThesisModel(status="needs_review")
    if source.suffix.lower() != ".pdf":
        model.status = "failed"
        model.extraction_warnings.append(f"PDF extraction failed: non-PDF input: {source}")
        return model

    source_copy = work / SOURCE_PDF_NAME
    try:
        if source.resolve(strict=False) != source_copy.resolve(strict=False):
            shutil.copy2(source, source_copy)
    except OSError as exc:
        model.status = "failed"
        model.extraction_warnings.append(f"PDF extraction failed: unable to copy source PDF: {exc}")
        return model

    try:
        import fitz
    except ImportError as exc:
        model.status = "failed"
        model.extraction_warnings.append(f"PDF extraction failed: PyMuPDF unavailable: {exc}")
        return model

    try:
        document = fitz.open(str(source_copy))
    except Exception as exc:
        model.status = "failed"
        model.extraction_warnings.append(f"PDF extraction failed: cannot open PDF: {exc}")
        return model

    try:
        if document.page_count == 0:
            model.status = "failed"
            model.extraction_warnings.append("PDF extraction failed: source has no pages")
            return model

        lines: list[PdfLine] = []
        line_index = 0
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_text = _page_text(page)
            if page_text:
                for text in page_text:
                    lines.append(PdfLine(index=line_index, page=page_index + 1, text=text))
                    line_index += 1
                model.figures.extend(_extract_page_figures(page, work, page_index + 1))
            else:
                figure = _render_page_image(page, work, page_index + 1)
                model.figures.append(figure)
                model.extraction_warnings.append(
                    f"OCR required: PDF page {page_index + 1} has no extractable text; page image rendered for review."
                )

        if lines:
            model.metadata = _extract_metadata(lines)
            model.sections, model.references = _extract_content(lines)
            model.sections, model.tables = _extract_tables_from_sections(model.sections)
            model.extraction_warnings.append(
                "PDF input converted through text extraction; layout review required against the source PDF."
            )
        else:
            model.extraction_warnings.append(
                "OCR required: PDF has no extractable text; generated Word/TeX content uses rendered page images only."
            )

        if any(figure.type == "pdf-figure-image" for figure in model.figures):
            model.extraction_warnings.append(
                "PDF embedded figures extracted as cropped images; captions and placement require review."
            )
        if model.tables:
            model.extraction_warnings.append(
                "PDF tabular text converted to editable tables; structure requires review."
            )
        model.extraction_warnings.extend(_metadata_warnings(model.metadata))
        if not model.sections and not model.figures:
            model.extraction_warnings.append("missing PDF body content")
        return model
    finally:
        document.close()


def _page_text(page) -> list[str]:
    raw = page.get_text("text") or ""
    lines = [_clean_text(line) for line in raw.splitlines()]
    return [line for line in lines if line]


def _render_page_image(page, work_dir: Path, page_number: int) -> AssetItem:
    image_dir = work_dir / "pdf-pages"
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / f"pdf-page-{page_number:03d}.png"
    try:
        import fitz

        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        pixmap.save(str(image_path))
    except Exception:
        image_path.write_bytes(b"")

    return AssetItem(
        id=f"pdf-page-{page_number}",
        type="pdf-page-image",
        path=str(image_path),
        caption=f"PDF page {page_number} image; OCR/manual transcription required",
        source=SourceEvidence(
            file=SOURCE_PDF_NAME,
            method="pdf-page-render",
            page_hint=page_number,
            confidence=0.35,
            requires_review=True,
        ),
        requires_review=True,
    )


def _extract_page_figures(page, work_dir: Path, page_number: int) -> list[AssetItem]:
    try:
        import fitz

        layout = page.get_text("dict")
    except Exception:
        return []

    text_blocks = _text_blocks_from_layout(layout)
    candidates: list[PdfImageCandidate] = []
    image_index = 0
    for block in layout.get("blocks", []):
        if block.get("type") != 1:
            continue
        bbox = _bbox_tuple(block.get("bbox"))
        if bbox is None:
            continue
        caption = _nearest_figure_caption(bbox, text_blocks)
        if _skip_pdf_image_block(bbox, page.rect, caption):
            continue
        image_index += 1
        candidates.append(
            PdfImageCandidate(
                index=image_index,
                page=page_number,
                bbox=bbox,
                caption=caption,
            )
        )

    if not candidates:
        return []

    image_dir = work_dir / "pdf-figures"
    image_dir.mkdir(parents=True, exist_ok=True)
    figures: list[AssetItem] = []
    for group_index, group in enumerate(_group_image_candidates(candidates), start=1):
        clip = _figure_clip_rect(fitz, page.rect, [candidate.bbox for candidate in group])
        if clip.width <= 1 or clip.height <= 1:
            continue
        image_path = image_dir / f"pdf-figure-page-{page_number:03d}-{group_index:02d}.png"
        try:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
            pixmap.save(str(image_path))
        except Exception:
            continue
        caption = _common_caption(group)
        figures.append(
            AssetItem(
                id=f"pdf-figure-{page_number}-{group_index}",
                type="pdf-figure-image",
                path=str(image_path),
                caption=caption,
                source=SourceEvidence(
                    file=SOURCE_PDF_NAME,
                    method="pdf-embedded-image",
                    page_hint=page_number,
                    confidence=0.62 if caption else 0.45,
                    requires_review=True,
                ),
                requires_review=True,
            )
        )
    return figures


def _text_blocks_from_layout(layout: dict) -> list[PdfTextBlock]:
    blocks: list[PdfTextBlock] = []
    for block in layout.get("blocks", []):
        if block.get("type") != 0:
            continue
        bbox = _bbox_tuple(block.get("bbox"))
        if bbox is None:
            continue
        text = _clean_text(
            " ".join(
                str(span.get("text", ""))
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            )
        )
        if text:
            blocks.append(PdfTextBlock(bbox=bbox, text=text))
    return blocks


def _bbox_tuple(value) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def _nearest_figure_caption(
    image_bbox: tuple[float, float, float, float],
    text_blocks: list[PdfTextBlock],
) -> str:
    matches: list[tuple[float, PdfTextBlock]] = []
    for block in text_blocks:
        if not FIGURE_CAPTION_RE.match(block.text):
            continue
        vertical_gap = block.bbox[1] - image_bbox[3]
        if vertical_gap < -2 or vertical_gap > MAX_FIGURE_CAPTION_DISTANCE:
            continue
        if _horizontal_overlap(image_bbox, block.bbox) <= 0:
            continue
        matches.append((vertical_gap, block))
    if not matches:
        return ""
    return min(matches, key=lambda item: item[0])[1].text


def _skip_pdf_image_block(
    bbox: tuple[float, float, float, float],
    page_rect,
    caption: str,
) -> bool:
    area = _bbox_area(bbox)
    if area < MIN_DISPLAY_IMAGE_AREA:
        return True
    if caption:
        return False
    if _is_page_sized_image(bbox, page_rect):
        return True
    if _is_header_footer_image(bbox, page_rect):
        return True
    return area < LARGE_UNCAPTIONED_IMAGE_AREA


def _is_page_sized_image(bbox: tuple[float, float, float, float], page_rect) -> bool:
    page_width = max(1.0, float(getattr(page_rect, "width", 0.0)))
    page_height = max(1.0, float(getattr(page_rect, "height", 0.0)))
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    area_ratio = _bbox_area(bbox) / (page_width * page_height)
    return (width / page_width >= 0.82 and height / page_height >= 0.82) or area_ratio >= 0.72


def _is_header_footer_image(bbox: tuple[float, float, float, float], page_rect) -> bool:
    page_top = float(getattr(page_rect, "y0", 0.0))
    page_bottom = float(getattr(page_rect, "y1", 0.0))
    return bbox[3] <= page_top + 130.0 or bbox[1] >= page_bottom - 90.0


def _group_image_candidates(candidates: list[PdfImageCandidate]) -> list[list[PdfImageCandidate]]:
    groups: list[list[PdfImageCandidate]] = []
    by_key: dict[tuple[int, str], list[PdfImageCandidate]] = {}
    for candidate in candidates:
        if candidate.caption:
            key = (candidate.page, candidate.caption)
        else:
            key = (candidate.page, f"uncaptioned-{candidate.index}")
        if key not in by_key:
            by_key[key] = []
            groups.append(by_key[key])
        by_key[key].append(candidate)
    return groups


def _figure_clip_rect(fitz, page_rect, boxes: list[tuple[float, float, float, float]]):
    padding = 2.0
    x0 = max(float(page_rect.x0), min(box[0] for box in boxes) - padding)
    y0 = max(float(page_rect.y0), min(box[1] for box in boxes) - padding)
    x1 = min(float(page_rect.x1), max(box[2] for box in boxes) + padding)
    y1 = min(float(page_rect.y1), max(box[3] for box in boxes) + padding)
    return fitz.Rect(x0, y0, x1, y1)


def _common_caption(candidates: list[PdfImageCandidate]) -> str:
    for candidate in candidates:
        if candidate.caption:
            return candidate.caption
    return ""


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _horizontal_overlap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    return max(0.0, min(left[2], right[2]) - max(left[0], right[0]))


def _extract_metadata(lines: list[PdfLine]) -> Metadata:
    metadata = Metadata()
    for field, labels in FIELD_LABELS.items():
        for line in lines[:120]:
            value = _extract_labeled_value(line.text, labels)
            if not value:
                continue
            if field == "student_id":
                match = re.search(r"\d{8,10}", value)
                value = match.group(0) if match else ""
            if not value:
                continue
            setattr(metadata, field, value)
            metadata.evidence[field] = SourceEvidence(
                file=SOURCE_PDF_NAME,
                method="pdf-text-label",
                paragraph_index=line.index,
                page_hint=line.page,
                confidence=0.7,
                requires_review=True,
            )
            break

    _apply_cover_metadata_heuristics(metadata, lines)

    if not metadata.title_cn and not metadata.title_en:
        guessed = _guess_title(lines)
        if guessed is not None:
            if _contains_cjk(guessed.text):
                metadata.title_cn = guessed.text
                evidence_key = "title_cn"
            else:
                metadata.title_en = guessed.text
                evidence_key = "title_en"
            metadata.evidence[evidence_key] = SourceEvidence(
                file=SOURCE_PDF_NAME,
                method="pdf-title-heuristic",
                paragraph_index=guessed.index,
                page_hint=guessed.page,
                confidence=0.4,
                requires_review=True,
            )

    if not metadata.unit_code:
        metadata.unit_code = "10006"
        metadata.evidence["unit_code"] = SourceEvidence(
            file=SOURCE_PDF_NAME,
            method="metadata-default",
            confidence=0.6,
            requires_review=False,
        )
    return metadata


def _apply_cover_metadata_heuristics(metadata: Metadata, lines: list[PdfLine]) -> None:
    texts = [line.text for line in lines]

    for index, text in enumerate(texts[:120]):
        field = NEXT_LINE_LABELS.get(text)
        if not field:
            continue
        value_line = _next_value_line(lines, index + 1)
        if value_line is not None:
            _set_metadata_field(metadata, field, value_line.text, value_line, "pdf-next-line-label")

    for index in range(min(len(lines), 120)):
        for tokens, field in VERTICAL_FIELD_LABELS:
            if tuple(texts[index : index + len(tokens)]) != tokens:
                continue
            value_line = _next_value_line(lines, index + len(tokens))
            if value_line is not None:
                _set_metadata_field(metadata, field, value_line.text, value_line, "pdf-vertical-label")

    if not metadata.date:
        for line in lines[:120]:
            match = re.search(r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?", line.text)
            if match:
                _set_metadata_field(metadata, "date", match.group(0), line, "pdf-date-line")
                break

    if not metadata.title_cn:
        title_line = _title_after_anchor(lines)
        if title_line is not None:
            title_text = title_line.text
            metadata.title_cn = title_text
            metadata.evidence["title_cn"] = SourceEvidence(
                file=SOURCE_PDF_NAME,
                method="pdf-cover-title-anchor",
                paragraph_index=title_line.index,
                page_hint=title_line.page,
                confidence=0.55,
                requires_review=True,
            )


def _next_value_line(lines: list[PdfLine], start: int) -> PdfLine | None:
    for line in lines[start : min(len(lines), start + 8)]:
        if not line.text:
            continue
        if _is_cover_label_fragment(line.text):
            continue
        return line
    return None


def _set_metadata_field(
    metadata: Metadata,
    field: str,
    value: str,
    line: PdfLine,
    method: str,
) -> None:
    if getattr(metadata, field):
        return
    cleaned = _clean_metadata_value(field, value)
    if not cleaned:
        return
    setattr(metadata, field, cleaned)
    metadata.evidence[field] = SourceEvidence(
        file=SOURCE_PDF_NAME,
        method=method,
        paragraph_index=line.index,
        page_hint=line.page,
        confidence=0.55,
        requires_review=True,
    )


def _clean_metadata_value(field: str, value: str) -> str:
    text = _clean_text(value).strip(" :：-")
    if field in {"student_id", "unit_code"}:
        width = 8 if field == "student_id" else 5
        match = re.search(rf"\d{{{width},10}}", text)
        return match.group(0) if match else ""
    if field == "date":
        text = re.sub(r"\s+", "", text)
    return text


def _title_after_anchor(lines: list[PdfLine]) -> PdfLine | None:
    texts = [line.text for line in lines]
    for index, text in enumerate(texts[:80]):
        if text not in TITLE_ANCHORS:
            continue
        title_parts: list[str] = []
        for candidate_index in range(index + 1, min(len(lines), index + 8)):
            if _starts_vertical_label_at(texts, candidate_index):
                break
            candidate = lines[candidate_index].text
            if _is_title_stop_line(candidate):
                break
            title_parts.append(candidate)
        title = "".join(title_parts).strip()
        if title:
            return PdfLine(lines[index + 1].index, lines[index + 1].page, title)
    return None


def _extract_labeled_value(text: str, labels: Iterable[str]) -> str:
    for label in sorted(labels, key=len, reverse=True):
        pattern = rf"^\s*{re.escape(label)}\s*[:：\-]\s*(.+?)\s*$"
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_text(match.group(1)).strip(" :：-")
    return ""


def _guess_title(lines: list[PdfLine]) -> PdfLine | None:
    for line in lines[:30]:
        if _is_metadata_line(line.text) or _is_title_stop_line(line.text):
            continue
        if 4 <= len(line.text) <= 120:
            return line
    return None


def _extract_content(lines: list[PdfLine]) -> tuple[list[ContentBlock], list[ContentBlock]]:
    sections: list[ContentBlock] = []
    references: list[ContentBlock] = []
    current_title = "PDF Extracted Text"
    current_title_page: int | None = None
    current_text: list[str] = []
    in_references = False
    in_toc = False

    content_lines = _merge_split_headings(_content_lines_without_buaa_cover_spine(lines))
    index = 0
    while index < len(content_lines):
        line = content_lines[index]
        previous_line = content_lines[index - 1] if index > 0 else None
        following_line = content_lines[index + 1] if index + 1 < len(content_lines) else None
        index += 1
        text = line.text
        if _is_running_header_footer_line(line, previous_line, following_line):
            continue
        if _is_metadata_line(text):
            continue
        if _is_toc_heading(text):
            _flush_section(sections, current_title, current_text, line)
            current_title = "PDF Extracted Text"
            current_title_page = None
            current_text = []
            in_toc = True
            continue
        if in_toc:
            following = content_lines[index] if index < len(content_lines) else None
            if following is not None and _can_merge_numbered_heading(line, following):
                candidate_text = f"{text} {following.text}"
                if _looks_like_heading(candidate_text) and not _looks_like_toc_entry(candidate_text):
                    line = PdfLine(index=line.index, page=line.page, text=candidate_text)
                    text = candidate_text
                    index += 1
                    in_toc = False
                else:
                    continue
            elif not _looks_like_heading(text) or _looks_like_toc_entry(text):
                continue
            else:
                in_toc = False
        if _is_front_matter_heading(text):
            _flush_section(sections, current_title, current_text, line)
            current_title = text
            current_title_page = line.page
            current_text = []
            continue
        if text.strip().casefold() in REFERENCE_HEADINGS:
            _flush_section(sections, current_title, current_text, line)
            current_text = []
            in_references = True
            continue
        if in_references:
            if text:
                references.append(
                    ContentBlock(
                        id=f"ref-{len(references) + 1}",
                        type="reference",
                        text=text,
                        source=_line_source(line, "pdf-reference-text"),
                    )
                )
            continue
        if _looks_like_heading(text):
            _flush_section(sections, current_title, current_text, line)
            current_title = text
            current_title_page = line.page
            current_text = []
            continue
        if _is_front_matter_spillover(current_title, current_title_page, line):
            continue
        current_text.append(text)

    if not in_references or current_text:
        last = lines[-1] if lines else None
        _flush_section(sections, current_title, current_text, last)
    return sections, references


def _extract_tables_from_sections(sections: list[ContentBlock]) -> tuple[list[ContentBlock], list[ContentBlock]]:
    rendered_sections: list[ContentBlock] = []
    tables: list[ContentBlock] = []
    for section in sections:
        lines = [line for line in str(section.text or "").splitlines()]
        if not lines:
            rendered_sections.append(section)
            continue

        kept_lines: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if not _is_table_caption(line):
                kept_lines.append(lines[index])
                index += 1
                continue

            table_rows: list[str] = []
            cursor = index + 1
            while cursor < len(lines) and _is_tabular_text_line(lines[cursor]):
                table_rows.append(_normalize_table_row(lines[cursor]))
                cursor += 1

            if len(table_rows) < 2:
                kept_lines.append(lines[index])
                index += 1
                continue

            tables.append(
                ContentBlock(
                    id=f"pdf-table-{len(tables) + 1}",
                    type="table",
                    title=line,
                    text="\n".join(table_rows),
                    level=section.level,
                    source=_table_source(section),
                )
            )
            index = cursor

        rendered_sections.append(
            ContentBlock(
                id=section.id,
                type=section.type,
                title=section.title,
                text="\n".join(line for line in kept_lines if line).strip(),
                level=section.level,
                source=section.source,
            )
        )
    return rendered_sections, tables


def _is_table_caption(text: str) -> bool:
    return bool(TABLE_CAPTION_RE.match(str(text or "").strip()))


def _is_tabular_text_line(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return "\t" in value or "|" in value or bool(re.search(r"\S\s{2,}\S", value))


def _normalize_table_row(text: str) -> str:
    value = str(text or "").strip()
    if "\t" in value:
        cells = value.split("\t")
    elif "|" in value:
        cells = value.strip("|").split("|")
    else:
        cells = re.split(r"\s{2,}", value)
    return "\t".join(cell.strip() for cell in cells if cell.strip())


def _table_source(section: ContentBlock) -> SourceEvidence:
    source = section.source
    return SourceEvidence(
        file=SOURCE_PDF_NAME,
        method="pdf-table-text",
        paragraph_index=source.paragraph_index if source else None,
        page_hint=source.page_hint if source else None,
        confidence=0.55,
        requires_review=True,
    )


def _merge_split_headings(lines: list[PdfLine]) -> list[PdfLine]:
    merged: list[PdfLine] = []
    index = 0
    while index < len(lines):
        current = lines[index]
        following = lines[index + 1] if index + 1 < len(lines) else None
        pair = (current.text, following.text) if following is not None else None
        if following is not None and pair in SPLIT_HEADING_PAIRS:
            merged.append(
                PdfLine(
                    index=current.index,
                    page=current.page,
                    text=SPLIT_HEADING_PAIRS[pair],
                )
            )
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def _can_merge_numbered_heading(current: PdfLine, following: PdfLine) -> bool:
    if current.page != following.page:
        return False
    if not re.fullmatch(r"\d+", current.text.strip()):
        return False
    if not following.text.strip() or re.match(r"^\d", following.text.strip()):
        return False
    return len(following.text.strip()) <= 80


def _content_lines_without_buaa_cover_spine(lines: list[PdfLine]) -> list[PdfLine]:
    if not _looks_like_buaa_cover_with_spine(lines):
        return lines

    start_index = _first_line_after_buaa_cover_spine(lines)
    if start_index is None:
        return lines
    return lines[start_index:]


def _looks_like_buaa_cover_with_spine(lines: list[PdfLine]) -> bool:
    first_lines = lines[:160]
    has_cover_anchor = any(line.text in TITLE_ANCHORS for line in first_lines)
    has_spine_marker = any(BUAA_SPINE_MARKER in line.text for line in first_lines)
    return has_cover_anchor and has_spine_marker


def _first_line_after_buaa_cover_spine(lines: list[PdfLine]) -> int | None:
    for index, line in enumerate(lines):
        if line.page <= 2:
            continue
        if line.text == "北京航空航天大学" and _next_line_contains(lines, index, BUAA_TASK_BOOK_TITLE):
            return index
        if BUAA_TASK_BOOK_TITLE in line.text:
            return max(0, index - 1) if index > 0 and lines[index - 1].text == "北京航空航天大学" else index
        if line.text in {"摘 要", "摘要", "ABSTRACT", "Abstract"}:
            return index
        if line.page > 2 and _looks_like_heading(line.text):
            return index

    for index, line in enumerate(lines):
        if line.page > 2:
            return index
    return None


def _next_line_contains(lines: list[PdfLine], index: int, text: str) -> bool:
    return index + 1 < len(lines) and text in lines[index + 1].text


def _flush_section(
    sections: list[ContentBlock],
    title: str,
    text_lines: list[str],
    evidence_line: PdfLine | None,
) -> None:
    text = "\n".join(line for line in text_lines if line).strip()
    if not text and title == "PDF Extracted Text":
        return
    level = _heading_level(title) if _looks_like_heading(title) else 1
    sections.append(
        ContentBlock(
            id=f"section-{len(sections) + 1}",
            type="chapter" if level == 1 and _looks_like_heading(title) else "section",
            title=title,
            text=text,
            level=level,
            source=_line_source(evidence_line, "pdf-section-text") if evidence_line else None,
        )
    )


def _line_source(line: PdfLine | None, method: str) -> SourceEvidence | None:
    if line is None:
        return None
    return SourceEvidence(
        file=SOURCE_PDF_NAME,
        method=method,
        paragraph_index=line.index,
        page_hint=line.page,
        confidence=0.65,
        requires_review=True,
    )


def _metadata_warnings(metadata: Metadata) -> list[str]:
    warnings: list[str] = []
    for field in REQUIRED_METADATA:
        if not getattr(metadata, field):
            warnings.append(f"missing metadata field: {field}")
    if metadata.title_en and not metadata.title_cn:
        warnings.append("PDF title extracted as English title; Chinese title requires review")
    return warnings


def _looks_like_heading(text: str) -> bool:
    return bool(re.match(r"^\s*\d+(?:\.\d+)*\s+\S+", text))


def _heading_level(text: str) -> int:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)\s+\S+", text)
    if not match:
        return 1
    return match.group(1).count(".") + 1


def _is_toc_heading(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().casefold()
    return normalized in {heading.casefold() for heading in TOC_HEADINGS}


def _looks_like_toc_entry(text: str) -> bool:
    return bool(re.search(r"(?:\.{3,}|…{2,}|·{3,})\s*\d+\s*$", str(text or "")))


def _is_front_matter_heading(text: str) -> bool:
    return str(text or "").strip() in FRONT_MATTER_HEADINGS


def _is_front_matter_spillover(title: str, title_page: int | None, line: PdfLine) -> bool:
    if title_page is None:
        return False
    if title == "本人声明":
        return line.page != title_page
    if title == "摘要":
        return line.page != title_page and not _contains_cjk(line.text)
    return False


def _is_running_header_footer_line(
    line: PdfLine,
    previous_line: PdfLine | None,
    following_line: PdfLine | None,
) -> bool:
    text = str(line.text or "").strip()
    if any(text.startswith(prefix) for prefix in RUNNING_HEADER_PREFIXES):
        return True
    if text in PAGE_NUMBER_MARKERS:
        return True
    if not (_is_plain_page_number(text) or _is_roman_page_number(text)):
        return False
    previous_text = str(previous_line.text or "").strip() if previous_line else ""
    following_text = str(following_line.text or "").strip() if following_line else ""
    return previous_text in PAGE_NUMBER_MARKERS or following_text in PAGE_NUMBER_MARKERS


def _is_plain_page_number(text: str) -> bool:
    return bool(re.fullmatch(r"\d{1,4}", text))


def _is_roman_page_number(text: str) -> bool:
    return bool(re.fullmatch(r"[IVXLCDM]{1,8}", text, flags=re.IGNORECASE))


def _is_metadata_line(text: str) -> bool:
    return (
        text in NEXT_LINE_LABELS
        or text in TITLE_ANCHORS
        or any(_extract_labeled_value(text, labels) for labels in FIELD_LABELS.values())
    )


def _starts_vertical_label_at(texts: list[str], index: int) -> bool:
    for tokens, _field in VERTICAL_FIELD_LABELS:
        if tuple(texts[index : index + len(tokens)]) == tokens:
            return True
    return False


def _is_cover_label_fragment(text: str) -> bool:
    if text in NEXT_LINE_LABELS or text in TITLE_ANCHORS:
        return True
    return any(text in tokens for tokens, _field in VERTICAL_FIELD_LABELS)


def _is_title_stop_line(text: str) -> bool:
    normalized = _clean_text(text)
    if not normalized:
        return True
    if normalized in NEXT_LINE_LABELS or normalized in TITLE_ANCHORS:
        return True
    if "分类号" in normalized:
        return True
    if re.fullmatch(r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?", normalized):
        return True
    return False


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _clean_text(text: str) -> str:
    return re.sub(r"[^\S\t]+", " ", str(text).replace("\u3000", " ")).strip()


__all__ = ["extract_pdf_model"]
