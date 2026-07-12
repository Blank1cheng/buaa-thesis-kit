"""Template-first DOCX assembly helpers."""

from .fragment_loader import load_package_parts
from .fragment_merger import write_package_with_replaced_parts
from .media_importer import media_parts
from .placeholder_replace import replace_docx_placeholders
from .rels_importer import relationship_parts
from .section_manager import extract_last_section_properties
from .style_importer import style_parts

__all__ = [
    "extract_last_section_properties",
    "load_package_parts",
    "media_parts",
    "relationship_parts",
    "replace_docx_placeholders",
    "style_parts",
    "write_package_with_replaced_parts",
]
