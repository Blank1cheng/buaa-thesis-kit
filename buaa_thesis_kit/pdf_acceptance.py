from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PdfOutputInspection:
    blocking_items: list[str] = field(default_factory=list)
    manual_review: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PdfLineLayout:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float


FRONT_MATTER_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cover", ("毕业设计(论文)", "毕业设计（论文）", "Graduation Thesis")),
    ("spine", ("书脊", "Book Spine")),
    ("declaration", ("本人声明", "Declaration")),
    ("cn_abstract", ("摘要", "摘 要", "Chinese Abstract")),
    ("en_abstract", ("Abstract",)),
)
ORDERED_MARKERS = ("cover", "spine", "declaration", "cn_abstract", "en_abstract", "body")
COVER_TITLE_MARKERS = FRONT_MATTER_MARKERS[0][1]
COVER_GEOMETRY_BANDS: dict[str, tuple[float, float]] = {
    "cover_title": (285.0, 370.0),
    "thesis_title": (385.0, 505.0),
    "field_rows": (520.0, 675.0),
    "date": (680.0, 735.0),
}


def inspect_pdf_output(pdf_path: Path) -> PdfOutputInspection:
    """Check exported PDF front-matter markers are not collapsed onto one page."""
    result = PdfOutputInspection()
    path = Path(pdf_path)
    if not path.exists() or not path.is_file():
        result.blocking_items.append(f"pdf_output_missing: {path}")
        return result

    try:
        import fitz

        document = fitz.open(str(path))
    except Exception as exc:
        result.blocking_items.append(f"pdf_output_unreadable: {exc}")
        return result

    try:
        marker_pages = _marker_pages(document)
        cover_geometry_problems, cover_geometry_note = _cover_geometry_inspection(document, marker_pages)
    finally:
        document.close()

    collapsed_pages = _collapsed_marker_pages(marker_pages)
    for page_number, markers in collapsed_pages:
        result.blocking_items.append(
            f"pdf_layout_collapsed: page {page_number} contains multiple front-matter markers: {', '.join(markers)}"
        )

    order_problem = _marker_order_problem(marker_pages)
    if order_problem:
        result.blocking_items.append(order_problem)

    result.blocking_items.extend(cover_geometry_problems)

    if not result.blocking_items:
        if marker_pages:
            result.notes.append(
                "PDF layout validation passed: "
                + ", ".join(f"{name}=p{page}" for name, page in marker_pages.items())
            )
            if cover_geometry_note:
                result.notes.append(cover_geometry_note)
        else:
            result.manual_review.append("pdf_layout_markers_missing: front-matter markers were not detectable.")
    return result


def _marker_pages(document) -> dict[str, int]:
    marker_pages: dict[str, int] = {}
    for page_index in range(document.page_count):
        page_number = page_index + 1
        lines = _page_lines(document.load_page(page_index))
        for name, markers in FRONT_MATTER_MARKERS:
            if name not in marker_pages and _contains_exact_line(lines, markers):
                marker_pages[name] = page_number
        if "body" not in marker_pages and any(_is_body_heading(line) for line in lines):
            marker_pages["body"] = page_number
    return marker_pages


def _page_lines(page) -> list[str]:
    raw = page.get_text("text") or ""
    return [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines() if line.strip()]


def _page_line_layouts(page) -> list[PdfLineLayout]:
    lines: list[PdfLineLayout] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = _clean_line_text("".join(str(span.get("text", "")) for span in spans))
            if not text:
                continue
            bbox = line.get("bbox", (0, 0, 0, 0))
            try:
                x0, y0, x1, y1 = (float(value) for value in bbox)
            except (TypeError, ValueError):
                continue
            size = max((float(span.get("size", 0.0)) for span in spans), default=0.0)
            lines.append(PdfLineLayout(text=text, x0=x0, y0=y0, x1=x1, y1=y1, size=size))
    return lines


def _contains_exact_line(lines: list[str], markers: tuple[str, ...]) -> bool:
    normalized_lines = {line.casefold() for line in lines}
    return any(marker.casefold() in normalized_lines for marker in markers)


def _is_body_heading(line: str) -> bool:
    return bool(re.fullmatch(r"1(?:\.0)?\s+[\u4e00-\u9fffA-Za-z].{0,40}", str(line or "").strip()))


def _collapsed_marker_pages(marker_pages: dict[str, int]) -> list[tuple[int, list[str]]]:
    by_page: dict[int, list[str]] = {}
    for marker, page in marker_pages.items():
        by_page.setdefault(page, []).append(marker)
    return [
        (page, [marker for marker in ORDERED_MARKERS if marker in markers])
        for page, markers in sorted(by_page.items())
        if len(markers) > 1
    ]


def _marker_order_problem(marker_pages: dict[str, int]) -> str:
    previous_name = ""
    previous_page = 0
    for marker in ORDERED_MARKERS:
        page = marker_pages.get(marker)
        if page is None:
            continue
        if previous_page and page < previous_page:
            return (
                f"pdf_layout_order: marker {marker} appears on page {page} before "
                f"{previous_name} on page {previous_page}."
            )
        previous_name = marker
        previous_page = page
    return ""


def _cover_geometry_inspection(document, marker_pages: dict[str, int]) -> tuple[list[str], str]:
    cover_page = marker_pages.get("cover")
    if cover_page is None or cover_page < 1 or cover_page > document.page_count:
        return [], ""

    layouts = _page_line_layouts(document.load_page(cover_page - 1))
    measurements = _cover_geometry_measurements(layouts)
    problems = [
        f"pdf_cover_geometry: {name} y={value:.1f} outside template band {low:.0f}-{high:.0f}"
        for name, value in measurements.items()
        for low, high in [COVER_GEOMETRY_BANDS[name]]
        if value < low or value > high
    ]
    if problems or not measurements:
        return problems, ""
    note = "PDF cover geometry validation passed: " + ", ".join(
        f"{name}_y={value:.1f}" for name, value in measurements.items()
    )
    return [], note


def _cover_geometry_measurements(layouts: list[PdfLineLayout]) -> dict[str, float]:
    measurements: dict[str, float] = {}

    cover_title = _first_line_matching(layouts, lambda line: _line_contains_any(line, COVER_TITLE_MARKERS))
    if cover_title is not None:
        measurements["cover_title"] = cover_title.y0

    title_lines = [
        line
        for line in layouts
        if line.size >= 18.0 and not _line_contains_any(line, COVER_TITLE_MARKERS)
    ]
    if title_lines:
        measurements["thesis_title"] = min(line.y0 for line in title_lines)

    field_rows = [
        line
        for line in layouts
        if 13.0 <= line.size <= 17.0
        and not _looks_like_cover_date(line.text)
        and line.y0 >= 400.0
    ]
    if field_rows:
        measurements["field_rows"] = min(line.y0 for line in field_rows)

    date_line = _first_line_matching(layouts, lambda line: _looks_like_cover_date(line.text))
    if date_line is not None:
        measurements["date"] = date_line.y0

    return measurements


def _first_line_matching(layouts: list[PdfLineLayout], predicate) -> PdfLineLayout | None:
    for line in layouts:
        if predicate(line):
            return line
    return None


def _line_contains_any(line: PdfLineLayout, markers: tuple[str, ...]) -> bool:
    normalized = line.text.casefold()
    return any(marker.casefold() in normalized for marker in markers)


def _looks_like_cover_date(text: str) -> bool:
    value = _clean_line_text(text)
    return bool(re.search(r"\b\d{4}\s*(?:年|[-/])\s*\d{1,2}\s*(?:月)?\b", value))


def _clean_line_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


__all__ = ["PdfOutputInspection", "inspect_pdf_output"]
