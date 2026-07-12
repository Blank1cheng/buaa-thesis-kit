from __future__ import annotations


def media_parts(parts: dict[str, bytes]) -> dict[str, bytes]:
    """Return embedded media parts from a loaded DOCX package."""
    return {name: data for name, data in parts.items() if name.startswith("word/media/")}


__all__ = ["media_parts"]

