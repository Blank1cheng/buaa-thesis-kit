from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


KIT_ROOT = Path(__file__).resolve().parents[2]
FRONT_MATTER_TEMPLATE_DIR = KIT_ROOT / "templates" / "frontmatter"
LEGACY_FRONT_MATTER_TEMPLATE_DIR = KIT_ROOT / "templates" / "front_matter"
CAPTURED_FRONT_MATTER_TEMPLATE_DIR = KIT_ROOT / "templates" / "front_matter_captured"
FRONT_MATTER_LAYOUT_SPEC = FRONT_MATTER_TEMPLATE_DIR / "layout_spec.yaml"

RENDER_LEVEL_REQUIRED_PAGES = (
    "cover",
    "spine",
    "taskbook",
    "declaration",
    "abstract_cn",
    "abstract_en",
    "toc",
)
PAGE_ALIASES = {
    "task_book": "taskbook",
    "task-book": "taskbook",
    "task": "taskbook",
    "cn_abstract": "abstract_cn",
    "en_abstract": "abstract_en",
}

PLACEHOLDER_KEYS = (
    "UNIT_CODE",
    "STUDENT_ID",
    "CLASSIFICATION",
    "TITLE_CN",
    "TITLE_CN_LINE1",
    "TITLE_CN_LINE2",
    "COLLEGE",
    "MAJOR",
    "STUDENT_NAME",
    "ADVISOR",
    "DATE_YEAR_MONTH",
    "TASK_TITLE",
    "TASK_RAW_MATERIALS",
    "TASK_WORK_CONTENT",
    "TASK_REFERENCES",
    "DECLARATION_TEXT",
    "AUTHOR_NAME",
    "DECLARATION_DATE",
    "ABSTRACT_CN",
    "KEYWORDS_CN",
    "TITLE_EN_LINE1",
    "TITLE_EN_LINE2",
    "AUTHOR_EN",
    "TUTOR_EN",
    "ABSTRACT_EN",
    "KEYWORDS_EN",
)


@dataclass(frozen=True)
class RenderValidationConfig:
    max_anchor_offset_px: int = 10
    max_bbox_delta_px: int = 12
    render_zoom: float = 1.5
    front_pages_to_render: int = 12
    sample_mode: str = "full"


def normalize_frontmatter_pages(pages: list[str] | tuple[str, ...] | None = None) -> list[str]:
    if pages is None:
        return list(RENDER_LEVEL_REQUIRED_PAGES)
    normalized: list[str] = []
    for page in pages:
        value = str(page or "").strip().lower()
        if not value:
            continue
        value = PAGE_ALIASES.get(value, value)
        if value not in normalized:
            normalized.append(value)
    return normalized


def load_frontmatter_layout_spec(path: Path | None = None) -> dict[str, Any]:
    spec_path = Path(path) if path is not None else FRONT_MATTER_LAYOUT_SPEC
    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))
