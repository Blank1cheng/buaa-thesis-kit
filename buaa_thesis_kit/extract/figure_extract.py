from __future__ import annotations

import re
from pathlib import Path
from typing import Any


SUPPORTED_LATEX_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
CONVERTIBLE_LATEX_IMAGE_EXTENSIONS = {".wmf", ".emf"}
LATEX_USABLE_IMAGE_EXTENSIONS = SUPPORTED_LATEX_IMAGE_EXTENSIONS | CONVERTIBLE_LATEX_IMAGE_EXTENSIONS
FIGURE_CAPTION_RE = re.compile(
    r"^\s*(?:图|fig(?:ure)?\.?)\s*(?P<number>\d+(?:[.\-]\d+)*)(?:\s+(?P<caption>.+?)\s*)?$",
    re.IGNORECASE,
)


def caption_key(value: str) -> str:
    raw = str(value or "").strip()
    text = re.sub(r"\s+", "", raw)
    match = FIGURE_CAPTION_RE.match(raw)
    if match:
        caption = str(match.group("caption") or "").strip()
        return re.sub(r"\s+", "", caption) or f"figure-number:{match.group('number')}"
    return text


def figure_candidates(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for index, figure in enumerate(figures):
        path = str(figure.get("path") or figure.get("asset") or figure.get("asset_path") or "")
        caption = str(figure.get("caption") or "")
        candidates.append(
            {
                "id": figure.get("id") or f"fig-{index + 1}",
                "asset": path,
                "caption": caption,
                "number_hint": figure_number(caption),
                "supported": Path(path).suffix.lower() in LATEX_USABLE_IMAGE_EXTENSIONS,
                "conversion_required": Path(path).suffix.lower() in CONVERTIBLE_LATEX_IMAGE_EXTENSIONS,
                "requires_review": bool(figure.get("requires_review")) or not caption,
            }
        )
    return candidates


def bind_figures_to_captions(figures: list[dict[str, Any]], captions: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key: dict[str, list[dict[str, Any]]] = {}
    by_number: dict[str, list[dict[str, Any]]] = {}
    for figure in figures:
        caption = str(figure.get("caption") or "")
        if not caption:
            continue
        by_key.setdefault(caption_key(caption), []).append(figure)
        number = figure_number(caption)
        if number:
            by_number.setdefault(number, []).append(figure)
    bindings = []
    needs_review = []
    for caption in captions:
        key = caption_key(caption)
        number = figure_number(caption)
        candidates = by_key.get(key) or by_number.get(number) or []
        chosen = _first_supported(candidates)
        if chosen is None:
            needs_review.append({"caption": caption, "reason": "figure_asset_missing_or_unsupported"})
            continue
        caption_text = strip_caption_number(caption) or strip_caption_number(str(chosen.get("caption") or ""))
        bindings.append(
            {
                "type": "figure",
                "asset": str(chosen.get("path") or chosen.get("asset") or chosen.get("asset_path") or ""),
                "caption": caption_text,
                "number_hint": number,
                "source_page": None,
                "confidence": 0.85,
            }
        )
    return bindings, needs_review


def is_figure_caption(text: str) -> bool:
    return bool(FIGURE_CAPTION_RE.match(str(text or "").strip()))


def strip_caption_number(text: str) -> str:
    match = FIGURE_CAPTION_RE.match(str(text or "").strip())
    return str(match.group("caption") or "").strip() if match else str(text or "").strip()


def figure_number(text: str) -> str:
    match = FIGURE_CAPTION_RE.match(str(text or "").strip())
    return match.group("number") if match else ""


def _first_supported(figures: list[dict[str, Any]]) -> dict[str, Any] | None:
    for figure in figures:
        path = Path(str(figure.get("path") or figure.get("asset") or figure.get("asset_path") or ""))
        if path.suffix.lower() in LATEX_USABLE_IMAGE_EXTENSIONS:
            return figure
    return None
