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
NEXT_LINE_LABELS: dict[str, str] = {
    "单位代码": "unit_code",
    "学校代码": "unit_code",
}
VERTICAL_FIELD_LABELS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("学", "号"), "student_id"),
    (("学", "院", "名", "称"), "college"),
    (("专", "业", "名", "称"), "major"),
    (("学", "生", "姓", "名"), "student_name"),
    (("指", "导", "教", "师"), "advisor"),
)
TITLE_ANCHORS = {"毕业设计(论文)", "毕业设计（论文）", "本科毕业设计(论文)", "本科毕业设计（论文）"}


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
            else:
                figure = _render_page_image(page, work, page_index + 1)
                model.figures.append(figure)
                model.extraction_warnings.append(
                    f"OCR required: PDF page {page_index + 1} has no extractable text; page image rendered for review."
                )

        if lines:
            model.metadata = _extract_metadata(lines)
            model.sections, model.references = _extract_content(lines)
            model.extraction_warnings.append(
                "PDF input converted through text extraction; layout review required against the source PDF."
            )
        else:
            model.extraction_warnings.append(
                "OCR required: PDF has no extractable text; generated Word/TeX content uses rendered page images only."
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
    current_text: list[str] = []
    in_references = False

    for line in lines:
        text = line.text
        if _is_metadata_line(text):
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
            current_text = []
            continue
        current_text.append(text)

    if not in_references or current_text:
        last = lines[-1] if lines else None
        _flush_section(sections, current_title, current_text, last)
    return sections, references


def _flush_section(
    sections: list[ContentBlock],
    title: str,
    text_lines: list[str],
    evidence_line: PdfLine | None,
) -> None:
    text = "\n".join(line for line in text_lines if line).strip()
    if not text and title == "PDF Extracted Text":
        return
    sections.append(
        ContentBlock(
            id=f"section-{len(sections) + 1}",
            type="chapter" if _looks_like_heading(title) else "section",
            title=title,
            text=text,
            level=1,
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
    return re.sub(r"\s+", " ", str(text).replace("\u3000", " ")).strip()


__all__ = ["extract_pdf_model"]
