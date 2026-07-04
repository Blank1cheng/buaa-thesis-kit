from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path


def write_package_with_replaced_parts(template_path: Path, output_path: Path, replacements: dict[str, bytes]) -> None:
    """Write a DOCX package by copying a template and replacing selected parts."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="buaa_fragment_merge_") as temp_dir:
        temp_output = Path(temp_dir) / "merged.docx"
        with zipfile.ZipFile(template_path) as source, zipfile.ZipFile(temp_output, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                data = replacements.get(item.filename)
                target.writestr(item, data if data is not None else source.read(item.filename))
        shutil.move(str(temp_output), str(output))


__all__ = ["write_package_with_replaced_parts"]

