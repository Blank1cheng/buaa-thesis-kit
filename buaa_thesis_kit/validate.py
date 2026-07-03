from __future__ import annotations

from pathlib import Path
from typing import Any

from buaa_thesis_kit.pdf_export import _verify_pdf_file


ALLOWED_TOP_LEVEL = {"thesis.docx", "thesis.pdf", "thesis.tex", "report.md", "image"}
REQUIRED_FILES = ("thesis.docx", "thesis.pdf", "thesis.tex", "report.md")
REQUIRED_REPORT_OUTPUT_ALIASES = (
    ("word", "thesis.docx"),
    ("pdf", "thesis.pdf"),
    ("tex", "thesis.tex"),
    ("image",),
)
PROCESS_FILE_SUFFIXES = {
    ".aux",
    ".bak",
    ".cache",
    ".docx",
    ".fls",
    ".json",
    ".log",
    ".md",
    ".markdown",
    ".out",
    ".pdf",
    ".synctex",
    ".synctex.gz",
    ".tex",
    ".tmp",
    ".toc",
    ".txt",
    ".yaml",
    ".yml",
}
PROCESS_DIR_NAMES = {"report", "debug", "cache", "__pycache__", ".pytest_cache"}
PROCESS_FILE_NAMES = {"report", "debug", "cache"}


def validate_clean_output(output_dir: Path) -> tuple[bool, list[str]]:
    output = Path(output_dir)
    messages: list[str] = []

    if not output.exists():
        return False, [f"Output directory missing: {output}"]
    if not output.is_dir():
        return False, [f"Output path is not a directory: {output}"]

    entries = {path.name: path for path in output.iterdir()}
    actual_names = set(entries)

    for missing in sorted(ALLOWED_TOP_LEVEL - actual_names):
        messages.append(f"Missing required output: {missing}")

    for unexpected in sorted(actual_names - ALLOWED_TOP_LEVEL):
        messages.append(f"Unexpected top-level output item: {unexpected}")

    for filename in REQUIRED_FILES:
        path = output / filename
        if not path.exists():
            continue
        if not path.is_file():
            messages.append(f"Required output must be a file: {filename}")
            continue
        if path.stat().st_size == 0:
            messages.append(f"Required output is empty: {filename}")
            continue
        if filename == "thesis.pdf":
            pdf_ok, pdf_reason = _verify_pdf_file(path)
            if not pdf_ok:
                messages.append(f"Invalid thesis.pdf: {pdf_reason}")

    image_dir = output / "image"
    if image_dir.exists() and not image_dir.is_dir():
        messages.append("image must be a directory")
    elif image_dir.is_dir():
        messages.extend(_validate_image_dir(image_dir))

    return not messages, messages


def build_report(
    source: str,
    outputs: dict[str, str],
    summary: dict[str, int],
    blocking_items: list[str],
    manual_review: list[str],
    notes: list[str],
) -> dict[str, Any]:
    output_statuses = [_normalize_status(status) for status in outputs.values()]
    missing_required = _missing_required_report_outputs(outputs)
    has_unknown_or_failed = any(status not in {"pass", "needs_review"} for status in output_statuses)

    if blocking_items or missing_required or has_unknown_or_failed:
        status = "failed"
    elif manual_review or any(status == "needs_review" for status in output_statuses):
        status = "needs_review"
    else:
        status = "pass"

    return {
        "status": status,
        "source": source,
        "outputs": outputs,
        "summary": summary,
        "blocking_items": blocking_items,
        "manual_review": manual_review,
        "notes": notes,
    }


def write_report_md(report: dict[str, Any], path: Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# BUAA Thesis Export Report",
        "",
        "Word is authoritative. PDF exported from Word. TeX auxiliary output is provided for review and recovery only.",
        "",
        "## Status",
        "",
        str(report.get("status", "unknown")),
        "",
        "## Outputs",
        "",
        *_format_mapping(report.get("outputs", {})),
        "",
        "## Summary",
        "",
        *_format_mapping(report.get("summary", {})),
        "",
        "## Blocking Items",
        "",
        *_format_list(report.get("blocking_items", [])),
        "",
        "## Manual Review",
        "",
        *_format_list(report.get("manual_review", [])),
        "",
        "## Notes",
        "",
        *_format_list(report.get("notes", [])),
        "",
    ]

    source = report.get("source")
    if source:
        lines.insert(4, f"Source: {source}")
        lines.insert(5, "")

    destination.write_text("\n".join(lines), encoding="utf-8")


def _validate_image_dir(image_dir: Path) -> list[str]:
    messages: list[str] = []
    for path in sorted(image_dir.rglob("*")):
        relative = path.relative_to(image_dir).as_posix()
        if _is_process_path(path, image_dir):
            messages.append(f"Process file is not allowed inside image/: {relative}")
    return messages


def _is_process_path(path: Path, image_dir: Path) -> bool:
    relative_parts = [part.lower() for part in path.relative_to(image_dir).parts]
    if path.is_dir() and path.name.lower() in PROCESS_DIR_NAMES:
        return True
    if any(part in PROCESS_DIR_NAMES for part in relative_parts[:-1]):
        return True

    name = path.name.lower()
    if path.is_file() and name in PROCESS_FILE_NAMES:
        return True
    if path.is_file() and _has_process_suffix(name):
        return True
    return False


def _missing_required_report_outputs(outputs: dict[str, str]) -> bool:
    normalized_keys = {str(key).strip().lower() for key in outputs}
    for aliases in REQUIRED_REPORT_OUTPUT_ALIASES:
        if not any(alias in normalized_keys for alias in aliases):
            return True
    return False


def _normalize_status(status: str) -> str:
    return str(status).strip().lower().replace("-", "_").replace(" ", "_")


def _has_process_suffix(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in PROCESS_FILE_SUFFIXES)


def _format_mapping(mapping: Any) -> list[str]:
    if not mapping:
        return ["- None"]
    return [f"- {key}: {value}" for key, value in mapping.items()]


def _format_list(items: Any) -> list[str]:
    if not items:
        return ["- None"]
    return [f"- {item}" for item in items]
