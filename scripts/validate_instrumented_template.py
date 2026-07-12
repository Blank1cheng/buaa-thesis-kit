from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import yaml
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.instrument_official_template import REQUIRED_PLACEHOLDERS  # noqa: E402


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
TEXT_TAGS = {
    f"{{{W_NS}}}t",
    f"{{{W_NS}}}instrText",
}
HARNESS_CONFIG_DIR = ROOT / "buaa_thesis_kit" / "harness" / "config"
VISIBLE_WORD_PARTS = (
    "word/document.xml",
    "word/header",
    "word/footer",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments.xml",
)


def validate_instrumented_template(
    template_path: Path,
    output_report: Path | None = None,
) -> dict[str, Any]:
    path = Path(template_path)
    failures: list[dict[str, Any]] = []
    checks: dict[str, Any] = {
        "docx_exists": path.exists(),
        "valid_docx": False,
        "required_placeholders": False,
        "template_forbidden_text": False,
        "reference_tail_clean": False,
        "toc_field": False,
        "page_number_fields": False,
        "headers_footers": False,
        "static_template_page_48": False,
        "toc_result_clean": False,
        "frontmatter_not_in_toc": False,
    }

    if not path.exists():
        failures.append({"id": "template_missing", "path": str(path)})
        return _report(path, checks, failures, output_report)

    try:
        parts = _read_word_xml_parts(path)
    except (OSError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        failures.append({"id": "invalid_docx", "detail": str(exc)})
        return _report(path, checks, failures, output_report)

    checks["valid_docx"] = True
    checks["headers_footers"] = any(
        name.startswith("word/header") or name.startswith("word/footer")
        for name in parts
    )
    if not checks["headers_footers"]:
        failures.append({"id": "headers_footers_missing"})

    visible_parts = {
        name: xml_bytes
        for name, xml_bytes in parts.items()
        if _is_visible_word_part(name)
    }
    visible_text = "\n".join(_xml_text(xml_bytes) for xml_bytes in visible_parts.values())
    leaked_tokens = [
        token
        for token in _template_forbidden_tokens()
        if token and token in visible_text
    ]
    checks["template_forbidden_text"] = not leaked_tokens
    if leaked_tokens:
        failures.append(
            {
                "id": "template_instructions_or_sample_leak",
                "tokens": sorted(set(leaked_tokens)),
            }
        )

    static_page_48 = re.search(r"第\s*48\s*页", visible_text)
    checks["static_template_page_48"] = static_page_48 is None
    if static_page_48:
        failures.append({"id": "static_template_page_48"})

    document_xml = parts.get("word/document.xml", b"")
    document_text = _xml_text(document_xml)
    toc_result_dirty = _toc_result_text(document_xml)
    checks["toc_result_clean"] = not toc_result_dirty.strip()
    if toc_result_dirty.strip():
        failures.append({"id": "toc_result_not_clean", "preview": toc_result_dirty[:200]})
    frontmatter_outline = _frontmatter_outline_text(document_xml)
    checks["frontmatter_not_in_toc"] = not frontmatter_outline.strip()
    if frontmatter_outline.strip():
        failures.append({"id": "frontmatter_outline_level_leak", "preview": frontmatter_outline[:200]})
    placeholders = _placeholders(document_text)
    missing_placeholders = sorted(REQUIRED_PLACEHOLDERS - placeholders)
    checks["required_placeholders"] = not missing_placeholders
    if missing_placeholders:
        failures.append(
            {
                "id": "required_placeholders_missing",
                "placeholders": missing_placeholders,
            }
        )

    reference_tail = _reference_tail_text(document_xml)
    checks["reference_tail_clean"] = not reference_tail.strip()
    if reference_tail.strip():
        failures.append(
            {
                "id": "reference_tail_not_clean",
                "preview": reference_tail[:200],
            }
        )

    checks["toc_field"] = _has_toc_field(document_xml)
    if not checks["toc_field"]:
        failures.append({"id": "toc_field_missing"})

    checks["page_number_fields"] = _has_page_number_field(parts)
    if not checks["page_number_fields"]:
        failures.append({"id": "page_number_field_missing"})

    return _report(path, checks, failures, output_report)


def validate_instrumented_template_file(template_path: Path) -> dict[str, Any]:
    return validate_instrumented_template(Path(template_path))


def _read_word_xml_parts(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as package:
        return {
            name: package.read(name)
            for name in package.namelist()
            if name.startswith("word/") and name.endswith(".xml")
        }


def _is_visible_word_part(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix) for prefix in VISIBLE_WORD_PARTS)


def _xml_text(xml_bytes: bytes) -> str:
    root = etree.fromstring(xml_bytes, etree.XMLParser(resolve_entities=False))
    return "\n".join((node.text or "") for node in root.iter() if node.tag in TEXT_TAGS)


def _reference_tail_text(document_xml: bytes) -> str:
    root = etree.fromstring(document_xml, etree.XMLParser(resolve_entities=False))
    body = root.find("w:body", NS)
    if body is None:
        return ""
    children = list(body)
    reference_index = None
    for index, child in enumerate(children):
        if child.tag == f"{{{W_NS}}}p" and "{{REFERENCES}}" in _element_text(child):
            reference_index = index
            break
    if reference_index is None:
        return ""
    tail: list[str] = []
    for child in children[reference_index + 1 :]:
        if child.tag == f"{{{W_NS}}}sectPr":
            continue
        text = _element_text(child).strip()
        if text:
            tail.append(text)
    return "\n".join(tail)


def _toc_result_text(document_xml: bytes) -> str:
    root = etree.fromstring(document_xml, etree.XMLParser(resolve_entities=False))
    body = root.find("w:body", NS)
    if body is None:
        return ""
    children = [child for child in body if child.tag == f"{{{W_NS}}}p"]
    toc_index = _find_toc_index(children)
    if toc_index is None:
        return ""
    body_start = _find_body_marker_index(children)
    if body_start is None:
        body_start = len(children)
    values = [
        _element_text(child).strip()
        for child in children[toc_index + 1 : body_start]
        if _element_text(child).strip()
    ]
    return "\n".join(values)


def _frontmatter_outline_text(document_xml: bytes) -> str:
    root = etree.fromstring(document_xml, etree.XMLParser(resolve_entities=False))
    body = root.find("w:body", NS)
    if body is None:
        return ""
    children = [child for child in body if child.tag == f"{{{W_NS}}}p"]
    toc_index = _find_toc_index(children)
    if toc_index is None:
        return ""
    values: list[str] = []
    for paragraph in children[:toc_index]:
        if paragraph.find("w:pPr/w:outlineLvl", NS) is not None:
            text = _element_text(paragraph).strip()
            if text:
                values.append(text)
    return "\n".join(values)


def _find_toc_index(paragraphs: list[etree._Element]) -> int | None:
    for index, paragraph in enumerate(paragraphs):
        text = "".join(_element_text(paragraph).split())
        if text.startswith("目录") or text.startswith("目錄") or text.startswith("目录TOC") or text.startswith("目錄TOC"):
            return index
    return None


def _find_body_marker_index(paragraphs: list[etree._Element]) -> int | None:
    for index, paragraph in enumerate(paragraphs):
        if "{{BODY_START}}" in _element_text(paragraph):
            return index
    return None


def _element_text(element: etree._Element) -> str:
    return "".join((node.text or "") for node in element.iter() if node.tag in TEXT_TAGS)


def _has_toc_field(document_xml: bytes) -> bool:
    text = document_xml.decode("utf-8", errors="ignore")
    return "TOC" in text and ("fldSimple" in text or "instrText" in text)


def _has_page_number_field(parts: dict[str, bytes]) -> bool:
    for name, xml_bytes in parts.items():
        if not (
            name == "word/document.xml"
            or name.startswith("word/header")
            or name.startswith("word/footer")
        ):
            continue
        text = xml_bytes.decode("utf-8", errors="ignore")
        if "PAGE" in text and ("fldSimple" in text or "instrText" in text):
            return True
    return False


def _placeholders(text: str) -> set[str]:
    result: set[str] = set()
    for chunk in text.split("{{")[1:]:
        name = chunk.split("}}", 1)[0]
        if name:
            result.add(name)
    return result


def _template_forbidden_tokens() -> list[str]:
    data = _load_yaml("template_sample_tokens.yaml")
    return [
        *[str(token) for token in data.get("template_instruction", [])],
        *[str(token) for token in data.get("template_sample_value", [])],
    ]


def _load_yaml(name: str) -> dict[str, Any]:
    path = HARNESS_CONFIG_DIR / name
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _report(
    template_path: Path,
    checks: dict[str, Any],
    failures: list[dict[str, Any]],
    output_report: Path | None,
) -> dict[str, Any]:
    report = {
        "status": "failed" if failures else "pass",
        "template": str(template_path),
        "checks": checks,
        "failures": failures,
    }
    if output_report is not None:
        path = Path(output_report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the purified official BUAA in-place template.")
    parser.add_argument("template", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    report = validate_instrumented_template(args.template, args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
