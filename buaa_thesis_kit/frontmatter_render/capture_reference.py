from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from buaa_thesis_kit.frontmatter_render.layout_spec import RENDER_LEVEL_REQUIRED_PAGES


DEFAULT_PAGE_RANGES = {
    "cover": (1, 1),
    "spine": (2, 2),
    "task_book": (3, 5),
    "declaration": (6, 6),
    "abstract_cn": (7, 8),
    "abstract_en": (9, 10),
    "toc": (11, 12),
}


@dataclass(frozen=True)
class CaptureResult:
    status: str
    outputs: dict[str, str]
    notes: list[str]


def capture_reference_frontmatter(reference_docx: Path, output_dir: Path) -> CaptureResult:
    """Capture front-matter page templates with Word COM when available.

    The current implementation performs capability checks and creates a manifest. Page-level
    capture is intentionally gated on Word COM, because LibreOffice page ranges are not stable
    enough for render templates.
    """
    reference = Path(reference_docx)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    outputs = {page: str(output / f"{page}.docx") for page in RENDER_LEVEL_REQUIRED_PAGES}
    notes: list[str] = []
    if not reference.exists():
        return CaptureResult("failed", outputs, [f"reference_docx_missing: {reference}"])
    ok, reason = _word_com_available()
    if not ok:
        notes.append(reason)
        notes.append("capture_frontmatter_template requires Word COM; use manual templates/front_matter/*.docx.")
        _write_manifest(output, reference, outputs, notes)
        return CaptureResult("needs_review", outputs, notes)
    notes.append("Word COM is available, but automated page-range capture is not yet enabled by default.")
    notes.append("Manual render templates remain authoritative until capture is reviewed.")
    _write_manifest(output, reference, outputs, notes)
    return CaptureResult("needs_review", outputs, notes)


def _word_com_available() -> tuple[bool, str]:
    try:
        import win32com.client  # type: ignore[import-not-found]  # noqa: F401
    except Exception as exc:
        return False, f"word_com_unavailable: {exc}"
    return True, "word_com_available"


def _write_manifest(output: Path, reference: Path, outputs: dict[str, str], notes: list[str]) -> None:
    lines = [
        "# Captured Front Matter Template Manifest",
        "",
        f"reference: {reference}",
        "",
        "## Expected Page Ranges",
        "",
    ]
    for page, page_range in DEFAULT_PAGE_RANGES.items():
        lines.append(f"- {page}: pages {page_range[0]}-{page_range[1]} -> {outputs[page]}")
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in notes)
    (output / "manifest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

