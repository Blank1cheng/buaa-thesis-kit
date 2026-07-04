from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


WORD_XML_PREFIXES = (
    "word/document.xml",
    "word/header",
    "word/footer",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments.xml",
)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
ET.register_namespace("w", W_NS)


def replace_docx_placeholders(
    source_docx: Path,
    output_docx: Path,
    replacements: dict[str, str],
) -> None:
    """Replace {{PLACEHOLDER}} text across all Word XML parts, including split runs."""
    source = Path(source_docx)
    output = Path(output_docx)
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        _placeholder_key(key): str(value or "")
        for key, value in replacements.items()
    }
    with tempfile.TemporaryDirectory(prefix="frontmatter-placeholders-") as temp:
        temp_dir = Path(temp)
        with zipfile.ZipFile(source) as package:
            package.extractall(temp_dir)
        for xml_path in _iter_word_xml_parts(temp_dir):
            _replace_xml_placeholders(xml_path, normalized)
        if output.exists():
            output.unlink()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
            for path in sorted(temp_dir.rglob("*")):
                if path.is_file():
                    package.write(path, path.relative_to(temp_dir).as_posix())


def replace_docx_placeholders_in_place(path: Path, replacements: dict[str, str]) -> None:
    temp = Path(tempfile.mkstemp(prefix="frontmatter-placeholders-", suffix=".docx")[1])
    try:
        replace_docx_placeholders(path, temp, replacements)
        shutil.move(str(temp), str(path))
    finally:
        if temp.exists():
            temp.unlink()


def _iter_word_xml_parts(root: Path):
    word_dir = root / "word"
    if not word_dir.exists():
        return
    for path in word_dir.glob("*.xml"):
        relative = path.relative_to(root).as_posix()
        if relative == "word/document.xml" or any(relative.startswith(prefix) for prefix in WORD_XML_PREFIXES[1:]):
            yield path


def _replace_xml_placeholders(path: Path, replacements: dict[str, str]) -> None:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except ET.ParseError:
        return
    changed = False
    for paragraph in root.findall(".//w:p", NS):
        if _replace_placeholders_in_container(paragraph, replacements):
            changed = True
    for text_box in root.findall(".//w:txbxContent", NS):
        if _replace_placeholders_in_container(text_box, replacements):
            changed = True
    if changed:
        path.write_text(
            ET.tostring(root, encoding="unicode", xml_declaration=True),
            encoding="utf-8",
            newline="",
        )


def _replace_placeholders_in_container(container, replacements: dict[str, str]) -> bool:
    text_nodes = container.findall(".//w:t", NS)
    if not text_nodes:
        return False
    original = "".join(node.text or "" for node in text_nodes)
    replaced = _replace_text(original, replacements)
    if replaced == original:
        return False
    first = text_nodes[0]
    first.text = replaced
    for node in text_nodes[1:]:
        node.text = ""
    return True


def _replace_text(text: str, replacements: dict[str, str]) -> str:
    result = text
    for key, value in replacements.items():
        result = result.replace(key, value)
    return result


def _placeholder_key(key: str) -> str:
    text = str(key)
    if text.startswith("{{") and text.endswith("}}"):
        return text
    return "{{" + text.strip("{}") + "}}"

