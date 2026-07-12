from __future__ import annotations

import zipfile
from pathlib import Path


def load_package_parts(docx_path: Path) -> dict[str, bytes]:
    """Load every part in a DOCX package keyed by ZIP part name."""
    with zipfile.ZipFile(docx_path) as package:
        return {name: package.read(name) for name in package.namelist() if not name.endswith("/")}


__all__ = ["load_package_parts"]

