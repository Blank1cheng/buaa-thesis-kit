from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from buaa_thesis_kit.latex_to_omml import latex_to_omml
from buaa_thesis_kit.models import ContentBlock, EquationItem, SourceEvidence


SOURCE_PDF_NAME = "source.pdf"
HEADER_FOOTER_TOP_RATIO = 0.075
HEADER_FOOTER_BOTTOM_RATIO = 0.94


@dataclass(frozen=True)
class PdfTextLine:
    index: int
    page: int
    text: str
    bbox: tuple[float, float, float, float] | None = None
    font: str = ""
    size: float = 0.0
    flags: int = 0
    page_width: float = 0.0
    page_height: float = 0.0


@dataclass
class ParsedPdfStructure:
    front_matter: dict[str, str] = field(default_factory=dict)
    sections: list[ContentBlock] = field(default_factory=list)
    references: list[ContentBlock] = field(default_factory=list)
    equations: list[EquationItem] = field(default_factory=list)
    kept_lines: list[PdfTextLine] = field(default_factory=list)
    removed_header_footer_lines: list[PdfTextLine] = field(default_factory=list)
    removed_toc_line_count: int = 0
    removed_field_code_line_count: int = 0


def parse_pdf_structure(
    lines: Iterable[PdfTextLine],
    *,
    source_file: str = SOURCE_PDF_NAME,
) -> ParsedPdfStructure:
    """Parse layout-aware PDF text lines into thesis structure."""
    result = ParsedPdfStructure()
    normalized_lines = _merge_split_headings(
        [line for line in lines if _clean_text(line.text)]
    )
    content_lines = _filter_header_footer(normalized_lines, result)

    mode: str | None = None
    current: ContentBlock | None = None
    current_text: list[str] = []
    active_abstract_key: str | None = None
    index = 0

    while index < len(content_lines):
        line = content_lines[index]
        text = _clean_text(line.text)
        index += 1

        if _is_field_code_line(text):
            result.removed_field_code_line_count += 1
            result.equations.append(
                _field_code_equation(text, line, len(result.equations) + 1, source_file)
            )
            continue

        if _is_toc_heading(text):
            _flush_section(result.sections, current, current_text)
            current = None
            current_text = []
            mode = "toc"
            result.removed_toc_line_count += 1
            continue

        if mode == "toc":
            if _looks_like_toc_entry(text):
                result.removed_toc_line_count += 1
                continue
            if not _looks_like_heading(text):
                result.removed_toc_line_count += 1
                continue
            mode = None

        abstract_key = _abstract_heading_key(text)
        if abstract_key:
            _flush_section(result.sections, current, current_text)
            current = None
            current_text = []
            mode = "abstract"
            active_abstract_key = abstract_key
            _append_inline_abstract_text(result.front_matter, abstract_key, text)
            continue

        keyword_key = _keyword_key(text)
        if keyword_key:
            value = _keyword_value(text)
            if value:
                result.front_matter[keyword_key] = value
            if mode == "abstract":
                mode = None
                active_abstract_key = None
            continue

        if mode == "abstract" and active_abstract_key:
            if _looks_like_heading(text) or _is_reference_heading(text) or _is_toc_heading(text):
                mode = None
                active_abstract_key = None
            else:
                _append_front_matter_line(result.front_matter, active_abstract_key, text)
                continue

        if _is_reference_heading(text):
            _flush_section(result.sections, current, current_text)
            current = None
            current_text = []
            mode = "references"
            continue

        if mode == "references":
            if text:
                result.references.append(
                    ContentBlock(
                        id=f"ref-{len(result.references) + 1}",
                        type="reference",
                        text=text,
                        source=_line_source(line, "pdf-reference-text", source_file),
                    )
                )
            continue

        if _is_front_matter_noise(text):
            continue

        if _looks_like_heading(text):
            _flush_section(result.sections, current, current_text)
            level = _heading_level(text)
            current = ContentBlock(
                id=f"section-{len(result.sections) + 1}",
                type="chapter" if level == 1 else "section",
                title=text,
                level=level,
                source=_line_source(line, "pdf-section-heading", source_file),
            )
            current_text = []
            mode = "body"
            continue

        if current is None:
            continue
        current_text.append(text)
        result.kept_lines.append(line)

    _flush_section(result.sections, current, current_text)
    return result


def write_structure_markdown(parsed: ParsedPdfStructure, path) -> None:
    """Write a temporary, reviewable extraction ledger outside the final output."""
    lines = ["# PDF Structured Extraction", ""]
    if parsed.front_matter:
        lines.extend(["## Front Matter", ""])
        for key, value in parsed.front_matter.items():
            lines.extend([f"### {key}", "", value, ""])
    lines.extend(["## Body", ""])
    for section in parsed.sections:
        if section.title:
            lines.extend([f"### {section.title}", ""])
        if section.text:
            lines.extend([section.text, ""])
    if parsed.equations:
        lines.extend(["## Equation Review", ""])
        for equation in parsed.equations:
            lines.append(f"- {equation.id}: {equation.text}")
        lines.append("")
    destination = path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")


def _filter_header_footer(
    lines: list[PdfTextLine],
    result: ParsedPdfStructure,
) -> list[PdfTextLine]:
    kept: list[PdfTextLine] = []
    for line in lines:
        if _is_header_footer_line(line):
            result.removed_header_footer_lines.append(line)
            continue
        kept.append(line)
    return kept


def _is_header_footer_line(line: PdfTextLine) -> bool:
    text = _clean_text(line.text)
    if not text:
        return True
    normalized = _compact(text)
    if normalized.startswith("北京航空航天大学毕业设计") or normalized.startswith("北京航空航天大学本科毕业设计"):
        return True
    if _is_page_number_line(text):
        return True
    if line.bbox is None or not line.page_height:
        return False
    y0 = line.bbox[1]
    y1 = line.bbox[3]
    top_cutoff = line.page_height * HEADER_FOOTER_TOP_RATIO
    bottom_cutoff = line.page_height * HEADER_FOOTER_BOTTOM_RATIO
    if y1 <= top_cutoff and len(text) <= 60:
        return True
    if y0 >= bottom_cutoff and (_is_page_number_line(text) or len(text) <= 20):
        return True
    return False


def _is_page_number_line(text: str) -> bool:
    value = _clean_text(text)
    return bool(
        re.fullmatch(r"\d{1,4}", value)
        or re.fullmatch(r"[IVXLCDM]{1,8}", value, flags=re.IGNORECASE)
        or re.fullmatch(r"第\s*(?:\d+|[IVXLCDM]+)\s*页", value, flags=re.IGNORECASE)
    )


def _abstract_heading_key(text: str) -> str:
    normalized = _compact(text).casefold()
    if normalized in {"摘要", "中文摘要"}:
        return "chinese_abstract"
    if normalized in {"abstract", "英文摘要"}:
        return "english_abstract"
    return ""


def _append_inline_abstract_text(front_matter: dict[str, str], key: str, text: str) -> None:
    value = re.sub(
        r"^(?:摘\s*要|中文摘要|Abstract|英文摘要)\s*[:：]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    if value and _compact(value).casefold() != _compact(text).casefold():
        _append_front_matter_line(front_matter, key, value)


def _append_front_matter_line(front_matter: dict[str, str], key: str, text: str) -> None:
    existing = front_matter.get(key, "")
    front_matter[key] = "\n".join(part for part in [existing, text] if part).strip()


def _keyword_key(text: str) -> str:
    value = _clean_text(text)
    if re.match(r"^(?:关键词|关键字)\s*[:：]", value):
        return "keywords_cn"
    if re.match(r"^key\s*words?\s*[:：]", value, flags=re.IGNORECASE):
        return "keywords_en"
    if re.match(r"^keywords\s*[:：]", value, flags=re.IGNORECASE):
        return "keywords_en"
    return ""


def _keyword_value(text: str) -> str:
    return re.sub(
        r"^(?:关键词|关键字|key\s*words?|keywords)\s*[:：]\s*",
        "",
        _clean_text(text),
        flags=re.IGNORECASE,
    ).strip()


def _is_toc_heading(text: str) -> bool:
    normalized = _compact(text).casefold()
    return normalized in {"目录", "contents", "tableofcontents"}


def _looks_like_toc_entry(text: str) -> bool:
    value = _clean_text(text)
    if re.search(r"(?:\.{2,}|…{2,}|·{2,})\s*\d+\s*$", value):
        return True
    return bool(re.match(r"^(?:\d+(?:\.\d+)*|第[一二三四五六七八九十百]+章|结论|致谢|参考文献)\s+.+\s+\d+\s*$", value))


def _is_reference_heading(text: str) -> bool:
    normalized = _compact(text).casefold()
    return normalized in {"参考文献", "references", "reference"}


def _is_front_matter_noise(text: str) -> bool:
    normalized = _compact(text)
    if not normalized:
        return True
    return normalized in {
        "本人声明",
        "北京航空航天大学",
        "本科毕业设计（论文）任务书",
        "本科毕业设计(论文)任务书",
    }


def _is_field_code_line(text: str) -> bool:
    value = _clean_text(text)
    return bool(
        "MERGEFORMAT" in value
        or value in {"公式章", "下一章"}
        or re.fullmatch(r"\d+\s*\\\*\s*MERGEFORMAT", value)
    )


def _field_code_equation(
    text: str,
    line: PdfTextLine,
    number: int,
    source_file: str,
) -> EquationItem:
    return EquationItem(
        id=f"pdf-field-code-{number}",
        kind="pdf-field-code",
        text=text,
        source=_line_source(line, "pdf-field-code", source_file, confidence=0.45),
        requires_review=True,
    )


def _looks_like_heading(text: str) -> bool:
    value = _clean_text(text)
    if _looks_like_toc_entry(value):
        return False
    numbered = re.match(r"^\d+(?:\.\d+)*\s+\S.{0,90}$", value)
    if numbered:
        return True
    if "。" in value or "." in value:
        return False
    return bool(re.match(r"^第[一二三四五六七八九十百]+章\s+\S.{0,40}$", value))


def _heading_level(text: str) -> int:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)\s+\S+", text)
    if match:
        return match.group(1).count(".") + 1
    return 1


def extract_equations_from_sections(
    sections: Iterable[ContentBlock],
    *,
    source_file: str = SOURCE_PDF_NAME,
    starting_number: int = 1,
) -> tuple[list[ContentBlock], list[EquationItem]]:
    rendered_sections: list[ContentBlock] = []
    equations: list[EquationItem] = []
    next_number = starting_number
    for section in sections:
        kept_lines: list[str] = []
        for line in str(section.text or "").splitlines():
            text = _clean_text(line)
            if _looks_like_equation_line(text):
                equations.append(_equation_from_pdf_line(text, section, next_number, source_file))
                next_number += 1
            else:
                kept_lines.append(line)

        rendered_sections.append(
            ContentBlock(
                id=section.id,
                type=section.type,
                title=section.title,
                text="\n".join(line for line in kept_lines if str(line).strip()).strip(),
                level=section.level,
                source=section.source,
            )
        )
    return rendered_sections, equations


def _looks_like_equation_line(text: str) -> bool:
    value = _clean_text(text)
    if not (3 <= len(value) <= 180):
        return False
    if _looks_like_heading(value):
        return False
    if re.search(r"[。；;，,]\s*$", value):
        return False
    if not re.search(r"[A-Za-z][A-Za-z0-9_{}()]*\s*(?:=|≤|<=|>=|≥|≈)", value):
        return False
    operator_count = len(re.findall(r"(?:=|≤|<=|>=|≥|≈|\+|-|\*|/|\^|_|\{|\})", value))
    if operator_count < 2:
        return False
    word_count = len(re.findall(r"[A-Za-z]+", value))
    return word_count <= 18


def _equation_from_pdf_line(
    text: str,
    section: ContentBlock,
    number: int,
    source_file: str,
) -> EquationItem:
    equation_text = _clean_text(text)
    equation_number = _extract_equation_number(equation_text)
    latex = equation_text
    if equation_number:
        latex = _clean_text(latex[: -len(equation_number)])
    omml = latex_to_omml(latex)
    requires_review = not bool(omml)

    return EquationItem(
        id=f"pdf-equation-{number}",
        kind="pdf-text-equation",
        text=equation_text,
        number=equation_number,
        latex=latex,
        omml=omml,
        source=_section_source(section, source_file, requires_review=requires_review),
        requires_review=requires_review,
    )


def _extract_equation_number(text: str) -> str:
    match = re.search(r"\((\d+(?:\.\d+)*)\)\s*$", str(text or "").strip())
    return match.group(0) if match else ""


def _section_source(
    section: ContentBlock,
    source_file: str,
    *,
    requires_review: bool,
) -> SourceEvidence:
    source = section.source
    return SourceEvidence(
        file=source_file,
        method="pdf-equation-text",
        paragraph_index=source.paragraph_index if source else None,
        page_hint=source.page_hint if source else None,
        confidence=0.5 if requires_review else 0.82,
        requires_review=requires_review,
    )


def _flush_section(
    sections: list[ContentBlock],
    current: ContentBlock | None,
    text_lines: list[str],
) -> None:
    if current is None:
        return
    current.text = "\n".join(line for line in text_lines if line).strip()
    sections.append(current)


def _line_source(
    line: PdfTextLine,
    method: str,
    source_file: str,
    *,
    confidence: float = 0.65,
) -> SourceEvidence:
    return SourceEvidence(
        file=source_file,
        method=method,
        paragraph_index=line.index,
        page_hint=line.page,
        confidence=confidence,
        requires_review=True,
    )


def _merge_split_headings(lines: list[PdfTextLine]) -> list[PdfTextLine]:
    merged: list[PdfTextLine] = []
    index = 0
    while index < len(lines):
        current = lines[index]
        following = lines[index + 1] if index + 1 < len(lines) else None
        if following is not None and _compact(current.text + following.text) in {"摘要", "目录"}:
            merged.append(
                PdfTextLine(
                    index=current.index,
                    page=current.page,
                    text=_compact(current.text + following.text),
                    bbox=_merged_bbox(current.bbox, following.bbox),
                    font=current.font,
                    size=max(current.size, following.size),
                    flags=current.flags,
                    page_width=current.page_width or following.page_width,
                    page_height=current.page_height or following.page_height,
                )
            )
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def _merged_bbox(
    left: tuple[float, float, float, float] | None,
    right: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float] | None:
    if left is None:
        return right
    if right is None:
        return left
    return (
        min(left[0], right[0]),
        min(left[1], right[1]),
        max(left[2], right[2]),
        max(left[3], right[3]),
    )


def _clean_text(text: str) -> str:
    return re.sub(r"[^\S\t]+", " ", str(text or "").replace("\u3000", " ")).strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


__all__ = [
    "ParsedPdfStructure",
    "PdfTextLine",
    "extract_equations_from_sections",
    "parse_pdf_structure",
    "write_structure_markdown",
]
