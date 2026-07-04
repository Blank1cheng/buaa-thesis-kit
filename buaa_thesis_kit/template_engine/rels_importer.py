from __future__ import annotations


def relationship_parts(parts: dict[str, bytes]) -> dict[str, bytes]:
    """Return package relationship parts from a loaded DOCX package."""
    return {name: data for name, data in parts.items() if "/_rels/" in name or name == "_rels/.rels"}


__all__ = ["relationship_parts"]

