from __future__ import annotations


def style_parts(parts: dict[str, bytes]) -> dict[str, bytes]:
    """Return style-related OOXML parts from a loaded DOCX package."""
    return {
        name: data
        for name, data in parts.items()
        if name in {"word/styles.xml", "word/numbering.xml"} or name.startswith("word/theme/")
    }


__all__ = ["style_parts"]

