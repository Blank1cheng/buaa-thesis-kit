from __future__ import annotations

import re
from collections.abc import Iterable


HEADER_FOOTER_PATTERNS = (
    re.compile(r"北京航空航天大学毕业设计\s*\(?论文\)?"),
    re.compile(r"^第\s*[IVXLCDM\d]+\s*页$"),
)
COVER_FIELD_LABELS = (
    "院（系）名称",
    "专业名称",
    "学生姓名",
    "指导教师",
)


def merge_pdf_lines(lines: Iterable[str], *, language: str = "auto") -> list[str]:
    """Merge hard PDF extraction lines into semantic Word paragraphs."""
    paragraphs: list[str] = []
    buffer: list[str] = []

    for raw_line in lines:
        line = str(raw_line or "").strip()
        if _is_discarded_line(line):
            continue
        if not line:
            _flush(paragraphs, buffer, language)
            continue
        if _starts_new_paragraph(line) and buffer:
            _flush(paragraphs, buffer, language)
        buffer.append(line)
        if _is_standalone_paragraph(line):
            _flush(paragraphs, buffer, language)

    _flush(paragraphs, buffer, language)
    return paragraphs


def merge_text(text: str, *, language: str = "auto") -> list[str]:
    return merge_pdf_lines(str(text or "").splitlines(), language=language)


def _flush(paragraphs: list[str], buffer: list[str], language: str) -> None:
    if not buffer:
        return
    merged = _join_lines(buffer, language=language).strip()
    if merged:
        paragraphs.append(merged)
    buffer.clear()


def _join_lines(lines: list[str], *, language: str) -> str:
    effective_language = _detect_language(lines) if language == "auto" else language
    merged = lines[0].strip()
    for line in lines[1:]:
        value = line.strip()
        if not value:
            continue
        if effective_language.startswith("zh"):
            merged += value
        elif merged.endswith("-") and value and value[0].islower():
            merged = merged[:-1] + value
        elif _adjacent_cjk(merged, value):
            merged += value
        else:
            merged += " " + value
    return merged


def _detect_language(lines: list[str]) -> str:
    text = "".join(lines)
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return "zh" if cjk_count >= latin_count else "en"


def _starts_new_paragraph(line: str) -> bool:
    return bool(
        line.startswith(("关键词", "Key Words", "Keywords", "Abstract", "摘"))
        or re.match(r"^\[\d+\]", line)
        or re.match(r"^(?:图|表|Fig\.|Table)\s*\d", line, flags=re.IGNORECASE)
        or re.match(r"^\d+(?:\.\d+)*\s+\S+", line)
    )


def _is_standalone_paragraph(line: str) -> bool:
    return bool(
        line.startswith(("关键词", "Key Words", "Keywords"))
        or re.match(r"^\[\d+\]", line)
        or re.match(r"^(?:图|表|Fig\.|Table)\s*\d", line, flags=re.IGNORECASE)
    )


def _is_discarded_line(line: str) -> bool:
    if not line:
        return False
    if any(pattern.search(line) for pattern in HEADER_FOOTER_PATTERNS):
        return True
    compact = re.sub(r"\s+", "", line)
    return any(re.sub(r"\s+", "", label) == compact for label in COVER_FIELD_LABELS)


def _adjacent_cjk(left: str, right: str) -> bool:
    return bool(
        left
        and right
        and re.search(r"[\u4e00-\u9fff]$", left)
        and re.match(r"^[\u4e00-\u9fff]", right)
    )


__all__ = ["merge_pdf_lines", "merge_text"]
