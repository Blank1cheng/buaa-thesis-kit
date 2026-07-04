from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from buaa_thesis_kit.models import AssetItem, ContentBlock, ThesisModel


@dataclass
class FigureTableInspection:
    blocking_items: list[str] = field(default_factory=list)
    manual_review: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


FIGURE_MARKER_RE = re.compile(
    r"(?:(?:\u56fe)|fig(?:ure)?\.?)\s*(\d+(?:[.\-]\d+)*)",
    flags=re.IGNORECASE,
)
TABLE_MARKER_RE = re.compile(
    r"(?:(?:\u8868)|table)\s*(\d+(?:[.\-]\d+)*)",
    flags=re.IGNORECASE,
)
FIGURE_CAPTION_RE = re.compile(
    r"^\s*(?:(?:\u56fe)|fig(?:ure)?\.?)\s*(\d+(?:[.\-]\d+)*)(?:\s+|$)",
    flags=re.IGNORECASE,
)
TABLE_CAPTION_RE = re.compile(
    r"^\s*(?:(?:\u8868)|table)\s*(\d+(?:[.\-]\d+)*)(?:\s+|$)",
    flags=re.IGNORECASE,
)


def inspect_figure_tables(model: ThesisModel) -> FigureTableInspection:
    """Check figure/table captions and cross-reference consistency."""
    result = FigureTableInspection()

    figure_numbers = _numbered_assets(model.figures, FIGURE_MARKER_RE)
    table_numbers = _numbered_blocks(model.tables, TABLE_MARKER_RE)
    body_lines = list(_body_lines(model))

    _inspect_duplicate_numbers(result, "figure", figure_numbers)
    _inspect_duplicate_numbers(result, "table", table_numbers)
    _inspect_uncaptioned_figures(result, model.figures)
    _inspect_untitled_tables(result, model.tables)

    _inspect_caption_without_asset(
        result,
        "figure",
        "Figure",
        _caption_numbers(body_lines, FIGURE_CAPTION_RE),
        set(figure_numbers),
    )
    _inspect_caption_without_asset(
        result,
        "table",
        "Table",
        _caption_numbers(body_lines, TABLE_CAPTION_RE),
        set(table_numbers),
    )
    _inspect_reference_without_target(
        result,
        "figure",
        "Figure",
        _reference_numbers(body_lines, FIGURE_MARKER_RE, FIGURE_CAPTION_RE),
        set(figure_numbers),
    )
    _inspect_reference_without_target(
        result,
        "table",
        "Table",
        _reference_numbers(body_lines, TABLE_MARKER_RE, TABLE_CAPTION_RE),
        set(table_numbers),
    )

    if not result.blocking_items and not result.manual_review and (model.figures or model.tables):
        result.notes.append(
            "figure/table validation passed: "
            f"{len(model.figures)} figure asset(s), {len(model.tables)} table(s)."
        )
    return result


def _inspect_duplicate_numbers(
    result: FigureTableInspection,
    kind: str,
    numbers: Iterable[str],
) -> None:
    for number, count in sorted(Counter(numbers).items()):
        if count > 1:
            label = "Figure" if kind == "figure" else "Table"
            result.blocking_items.append(f"duplicate_{kind}_number: {label} {number}")


def _inspect_uncaptioned_figures(
    result: FigureTableInspection,
    figures: Iterable[AssetItem],
) -> None:
    for figure in figures:
        if not _clean_text(figure.caption):
            result.manual_review.append(f"uncaptioned_figure_asset: {figure.id}")


def _inspect_untitled_tables(
    result: FigureTableInspection,
    tables: Iterable[ContentBlock],
) -> None:
    for table in tables:
        if not _clean_text(table.title):
            result.manual_review.append(f"untitled_table: {table.id}")


def _inspect_caption_without_asset(
    result: FigureTableInspection,
    kind: str,
    label: str,
    caption_numbers: set[str],
    asset_numbers: set[str],
) -> None:
    for number in sorted(caption_numbers - asset_numbers):
        result.blocking_items.append(f"{kind}_caption_without_asset: {label} {number}")


def _inspect_reference_without_target(
    result: FigureTableInspection,
    kind: str,
    label: str,
    reference_numbers: set[str],
    asset_numbers: set[str],
) -> None:
    for number in sorted(reference_numbers - asset_numbers):
        result.blocking_items.append(f"{kind}_reference_without_asset: {label} {number}")


def _numbered_assets(assets: Iterable[AssetItem], pattern: re.Pattern[str]) -> list[str]:
    numbers: list[str] = []
    seen_captioned_assets: set[tuple[str, str]] = set()
    for asset in assets:
        marker = _first_number(asset.caption, pattern)
        if marker:
            key = (marker, _clean_text(asset.caption).casefold())
            if key in seen_captioned_assets:
                continue
            seen_captioned_assets.add(key)
            numbers.append(marker)
    return numbers


def _numbered_blocks(blocks: Iterable[ContentBlock], pattern: re.Pattern[str]) -> list[str]:
    numbers: list[str] = []
    for block in blocks:
        marker = _first_number(block.title, pattern)
        if marker:
            numbers.append(marker)
    return numbers


def _caption_numbers(lines: Iterable[str], pattern: re.Pattern[str]) -> set[str]:
    numbers: set[str] = set()
    for line in lines:
        marker = _first_number(line, pattern)
        if marker:
            numbers.add(marker)
    return numbers


def _reference_numbers(
    lines: Iterable[str],
    marker_pattern: re.Pattern[str],
    caption_pattern: re.Pattern[str],
) -> set[str]:
    numbers: set[str] = set()
    for line in lines:
        if _first_number(line, caption_pattern):
            continue
        numbers.update(_normalize_number(match.group(1)) for match in marker_pattern.finditer(line))
    return {number for number in numbers if number}


def _first_number(text: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(str(text or ""))
    if not match:
        return ""
    return _normalize_number(match.group(1))


def _normalize_number(value: str) -> str:
    return str(value or "").strip().replace("-", ".")


def _body_lines(model: ThesisModel) -> Iterable[str]:
    for block in [*model.sections, *model.appendices]:
        for value in (block.title, block.text):
            for line in str(value or "").splitlines():
                cleaned = _clean_text(line)
                if cleaned:
                    yield cleaned


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


__all__ = ["FigureTableInspection", "inspect_figure_tables"]
