from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PdfOutputInspection:
    blocking_items: list[str] = field(default_factory=list)
    manual_review: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


FRONT_MATTER_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cover", ("毕业设计(论文)", "毕业设计（论文）", "Graduation Thesis")),
    ("spine", ("书脊", "Book Spine")),
    ("declaration", ("本人声明", "Declaration")),
    ("cn_abstract", ("摘要", "摘 要", "Chinese Abstract")),
    ("en_abstract", ("Abstract",)),
)
ORDERED_MARKERS = ("cover", "spine", "declaration", "cn_abstract", "en_abstract", "body")


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

    if not result.blocking_items:
        if marker_pages:
            result.notes.append(
                "PDF layout validation passed: "
                + ", ".join(f"{name}=p{page}" for name, page in marker_pages.items())
            )
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


__all__ = ["PdfOutputInspection", "inspect_pdf_output"]
