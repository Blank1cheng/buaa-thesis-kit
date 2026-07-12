from __future__ import annotations

from buaa_thesis_kit.frontmatter_render.layout_spec import (
    FRONT_MATTER_LAYOUT_SPEC,
    FRONT_MATTER_TEMPLATE_DIR,
    RENDER_LEVEL_REQUIRED_PAGES,
    RenderValidationConfig,
    load_frontmatter_layout_spec,
    normalize_frontmatter_pages,
)
from buaa_thesis_kit.frontmatter_render.replace_placeholders import (
    replace_docx_placeholders,
)
from buaa_thesis_kit.frontmatter_render.validate_render import (
    validate_render_frontmatter,
)

__all__ = [
    "FRONT_MATTER_TEMPLATE_DIR",
    "FRONT_MATTER_LAYOUT_SPEC",
    "RENDER_LEVEL_REQUIRED_PAGES",
    "RenderValidationConfig",
    "load_frontmatter_layout_spec",
    "normalize_frontmatter_pages",
    "replace_docx_placeholders",
    "validate_render_frontmatter",
]
