from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
SECT_PR = f"{{{W_NS}}}sectPr"
TEXT_TAGS = {
    f"{{{W_NS}}}t",
    f"{{{W_NS}}}instrText",
}

REQUIRED_FRAGMENTS = (
    "cover",
    "spine",
    "task_book",
    "declaration",
    "abstract_cn",
    "abstract_en",
    "toc",
    "body_base",
    "body_chapter_start",
    "body_section_flow",
    "body_figure_block",
    "body_table_block",
    "references",
    "acknowledgement",
    "appendix",
)

ANCHORS: dict[str, tuple[str, ...]] = {
    "cover": ("毕业设计(论文)", "毕业设计（论文）", "本科毕业设计"),
    "spine": ("论文封面书脊", "书脊"),
    "task_book": ("本科毕业设计（论文）任务书", "任务书"),
    "declaration": ("本人声明",),
    "abstract_cn": ("摘    要", "摘要"),
    "abstract_en": ("Abstract", "ABSTRACT"),
    "toc": ("目    录", "目录"),
    "body_base": ("1 绪论", "1  绪论", "第1章", "第一章"),
    "body_chapter_start": ("1 绪论", "1  绪论", "第1章", "第一章"),
    "body_section_flow": ("1.1", "1.1 ", "1.1\t"),
    "body_figure_block": ("图1.1", "图 1.1", "Fig. 1.1", "Figure 1.1"),
    "body_table_block": ("表1.1", "表 1.1", "Table 1.1"),
    "references": ("参考文献",),
    "acknowledgement": ("致谢",),
    "appendix": ("附录",),
}
ANCHOR_PATTERNS: dict[str, tuple[str, ...]] = {
    "body_section_flow": (r"^\d+\.\d+",),
    "body_figure_block": (r"^图[a-z]?\d+(?:\.\d+)*", r"^fig(?:ure)?\.?\d+(?:\.\d+)*"),
    "body_table_block": (r"^表[a-z]?\d+(?:\.\d+)*", r"^table\d+(?:\.\d+)*"),
}
CHAPTER_STYLE_IDS = {"Heading1", "1"}
FRONT_MATTER_SEQUENCE = (
    "cover",
    "spine",
    "task_book",
    "declaration",
    "abstract_cn",
    "abstract_en",
    "toc",
    "body_base",
    "acknowledgement",
    "references",
    "appendix",
)


def extract_render_fragments(template_path: Path, output_dir: Path) -> dict[str, Any]:
    """Split an official DOCX template into reusable render fragments."""
    template = Path(template_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    root = _read_document_root(template)
    body = root.find("w:body", NS)
    if body is None:
        raise ValueError(f"Invalid DOCX: word/document.xml has no w:body: {template}")

    body_children = list(body)
    sect_pr = _find_section_properties(body_children)
    content_children = [child for child in body_children if child.tag != SECT_PR]
    child_texts = [_element_text(child) for child in content_children]
    anchor_indexes = {
        name: _find_anchor_index(child_texts, ANCHORS[name], ANCHOR_PATTERNS.get(name, ()))
        for name in REQUIRED_FRAGMENTS
    }
    anchor_indexes = _refine_body_scoped_anchors(content_children, child_texts, anchor_indexes)

    manifest: dict[str, Any] = {
        "status": "pass",
        "source": str(template),
        "output_dir": str(out_dir),
        "missing_fragments": [],
        "fragments": {},
    }

    _copy_supporting_parts(template, out_dir)
    shutil.copy2(template, out_dir / "style_pack.docx")

    for fragment_name in REQUIRED_FRAGMENTS:
        start_index = anchor_indexes[fragment_name]
        if start_index is None:
            derived_children = _derive_fragment_children(fragment_name, content_children, anchor_indexes)
            if derived_children is None:
                manifest["missing_fragments"].append(fragment_name)
                manifest["fragments"][fragment_name] = {
                    "status": "missing_anchor",
                    "source": "official_template",
                    "anchors": list(ANCHORS[fragment_name]),
                }
                continue
            fragment_path = out_dir / f"{fragment_name}.docx"
            document_xml = _document_xml_with_children(root, derived_children, sect_pr)
            _write_docx_with_document_xml(template, fragment_path, document_xml)
            manifest["fragments"][fragment_name] = {
                "status": "derived_from_official_body_style",
                "source": "official_template",
                "output": str(fragment_path),
                "child_count": len(derived_children),
            }
            continue

        selected_children = _select_fragment_children(
            fragment_name,
            content_children,
            start_index,
            anchor_indexes,
        )
        if fragment_name == "toc" and not _children_have_field(selected_children):
            selected_children = [content_children[start_index], _toc_field_paragraph()]
        if fragment_name == "body_base":
            selected_children = [_placeholder_paragraph("{{BODY}}")]

        fragment_path = out_dir / f"{fragment_name}.docx"
        document_xml = _document_xml_with_children(root, selected_children, sect_pr)
        _write_docx_with_document_xml(template, fragment_path, document_xml)
        manifest["fragments"][fragment_name] = {
            "status": "pass",
            "source": "official_template",
            "output": str(fragment_path),
            "start_index": start_index,
            "child_count": len(selected_children),
        }

    if manifest["missing_fragments"]:
        manifest["status"] = "needs_review"
    _write_manifest(out_dir, manifest)
    return manifest


def _select_fragment_children(
    fragment_name: str,
    content_children: list[etree._Element],
    start_index: int,
    anchor_indexes: dict[str, int | None],
) -> list[etree._Element]:
    if fragment_name in {"body_chapter_start", "body_section_flow", "body_figure_block", "body_table_block"}:
        return [content_children[start_index]]

    end_index = _next_sequence_anchor(fragment_name, start_index, anchor_indexes, len(content_children))
    return content_children[start_index:end_index]


def _derive_fragment_children(
    fragment_name: str,
    content_children: list[etree._Element],
    anchor_indexes: dict[str, int | None],
) -> list[etree._Element] | None:
    if fragment_name != "acknowledgement":
        return None
    source_index = anchor_indexes.get("references") or anchor_indexes.get("appendix") or anchor_indexes.get("body_chapter_start")
    if source_index is None:
        return None
    title = _clone_with_text(content_children[source_index], "致谢")
    return [title, _placeholder_paragraph("{{ACKNOWLEDGEMENT}}")]


def _clone_with_text(element: etree._Element, text: str) -> etree._Element:
    clone = deepcopy(element)
    text_nodes = [node for node in clone.iter() if node.tag in TEXT_TAGS]
    if not text_nodes:
        return _placeholder_paragraph(text)
    text_nodes[0].text = text
    for node in text_nodes[1:]:
        node.text = ""
    return clone


def _refine_body_scoped_anchors(
    content_children: list[etree._Element],
    child_texts: list[str],
    anchor_indexes: dict[str, int | None],
) -> dict[str, int | None]:
    refined = dict(anchor_indexes)
    toc_index = refined.get("toc")
    body_start = _find_body_start_index(content_children, child_texts, toc_index)
    if body_start is None:
        return refined

    refined["body_base"] = body_start
    refined["body_chapter_start"] = body_start
    body_search_start = body_start + 1
    for fragment_name in (
        "body_section_flow",
        "body_figure_block",
        "body_table_block",
        "references",
        "acknowledgement",
        "appendix",
    ):
        refined[fragment_name] = _find_anchor_index_after(
            child_texts,
            ANCHORS[fragment_name],
            ANCHOR_PATTERNS.get(fragment_name, ()),
            body_search_start,
        )
    return refined


def _find_body_start_index(
    content_children: list[etree._Element],
    child_texts: list[str],
    toc_index: int | None,
) -> int | None:
    start = (toc_index + 1) if toc_index is not None else 0
    for index in range(start, len(content_children)):
        text = child_texts[index]
        if _looks_like_manual_toc_or_field(text):
            continue
        if _paragraph_style_id(content_children[index]) in CHAPTER_STYLE_IDS:
            return index
    return _find_anchor_index_after(
        child_texts,
        ANCHORS["body_chapter_start"],
        (r"^\d+\s+\S+",),
        start,
    )


def _next_sequence_anchor(
    fragment_name: str,
    start_index: int,
    anchor_indexes: dict[str, int | None],
    default_end: int,
) -> int:
    later_indexes: list[int] = []
    try:
        sequence_index = FRONT_MATTER_SEQUENCE.index(fragment_name)
    except ValueError:
        return min(start_index + 1, default_end)
    for later_name in FRONT_MATTER_SEQUENCE[sequence_index + 1 :]:
        index = anchor_indexes.get(later_name)
        if index is not None and index > start_index:
            later_indexes.append(index)
    return min(later_indexes) if later_indexes else min(start_index + 1, default_end)


def _read_document_root(template_path: Path) -> etree._Element:
    with zipfile.ZipFile(template_path) as package:
        document_xml = package.read("word/document.xml")
    return etree.fromstring(document_xml, etree.XMLParser(remove_blank_text=False, resolve_entities=False))


def _find_section_properties(children: list[etree._Element]) -> etree._Element | None:
    for child in reversed(children):
        if child.tag == SECT_PR:
            return child
    return None


def _element_text(element: etree._Element) -> str:
    return "".join((node.text or "") for node in element.iter() if node.tag in TEXT_TAGS)


def _find_anchor_index(child_texts: list[str], anchors: tuple[str, ...], patterns: tuple[str, ...] = ()) -> int | None:
    normalized_anchors = [_normalize_text(anchor) for anchor in anchors]
    for index, text in enumerate(child_texts):
        normalized_text = _normalize_text(text)
        if any(anchor and anchor in normalized_text for anchor in normalized_anchors):
            return index
        if any(re.search(pattern, normalized_text, flags=re.IGNORECASE) for pattern in patterns):
            return index
    return None


def _find_anchor_index_after(
    child_texts: list[str],
    anchors: tuple[str, ...],
    patterns: tuple[str, ...],
    start_index: int,
) -> int | None:
    normalized_anchors = [_normalize_text(anchor) for anchor in anchors]
    for index in range(start_index, len(child_texts)):
        text = child_texts[index]
        if _looks_like_manual_toc_or_field(text):
            continue
        normalized_text = _normalize_text(text)
        if any(anchor and anchor in normalized_text for anchor in normalized_anchors):
            return index
        if any(re.search(pattern, normalized_text, flags=re.IGNORECASE) for pattern in patterns):
            return index
    return None


def _paragraph_style_id(element: etree._Element) -> str:
    style = element.find("w:pPr/w:pStyle", NS)
    return style.get(f"{{{W_NS}}}val", "") if style is not None else ""


def _looks_like_manual_toc_or_field(text: str) -> bool:
    stripped = text.strip()
    normalized = _normalize_text(stripped)
    if not normalized:
        return True
    if normalized in {"toc1", "toc2", "toc3"}:
        return True
    if re.fullmatch(r"\d+", normalized):
        return True
    return ("…" in stripped or "..." in stripped) and bool(re.search(r"\d\s*$", stripped))


def _normalize_text(text: str) -> str:
    return "".join(text.split()).lower()


def _placeholder_paragraph(placeholder: str) -> etree._Element:
    return etree.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:r><w:t>{placeholder}</w:t></w:r></w:p>'.encode("utf-8")
    )


def _toc_field_paragraph() -> etree._Element:
    return etree.fromstring(
        (
            f'<w:p xmlns:w="{W_NS}"><w:fldSimple w:instr="TOC \\o &quot;1-3&quot; \\h \\z \\u">'
            "<w:r><w:t>TOC</w:t></w:r>"
            "</w:fldSimple></w:p>"
        ).encode("utf-8")
    )


def _children_have_field(children: list[etree._Element]) -> bool:
    for child in children:
        xml = etree.tostring(child, encoding="unicode")
        if "fldSimple" in xml or "instrText" in xml or "fldChar" in xml:
            return True
    return False


def _document_xml_with_children(
    source_root: etree._Element,
    children: list[etree._Element],
    sect_pr: etree._Element | None,
) -> bytes:
    new_root = deepcopy(source_root)
    new_body = new_root.find("w:body", NS)
    if new_body is None:
        raise ValueError("Invalid DOCX root: missing w:body")
    for child in list(new_body):
        new_body.remove(child)
    for child in children:
        new_body.append(deepcopy(child))
    if sect_pr is not None and not any(child.tag == SECT_PR for child in new_body):
        new_body.append(deepcopy(sect_pr))
    return etree.tostring(new_root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _write_docx_with_document_xml(template_path: Path, fragment_path: Path, document_xml: bytes) -> None:
    fragment_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template_path, "r") as source, zipfile.ZipFile(fragment_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = document_xml if item.filename == "word/document.xml" else source.read(item.filename)
            target.writestr(item, data)


def _copy_supporting_parts(template_path: Path, out_dir: Path) -> None:
    relationships_dir = out_dir / "relationships"
    media_dir = out_dir / "media"
    relationships_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    header_footer_parts: dict[str, str] = {}
    with zipfile.ZipFile(template_path) as package:
        names = set(package.namelist())
        if "word/styles.xml" in names:
            (out_dir / "styles.xml").write_bytes(package.read("word/styles.xml"))
        if "word/numbering.xml" in names:
            (out_dir / "numbering.xml").write_bytes(package.read("word/numbering.xml"))
        if "word/_rels/document.xml.rels" in names:
            (relationships_dir / "document.xml.rels").write_bytes(package.read("word/_rels/document.xml.rels"))
        for name in names:
            if name.startswith("word/media/") and not name.endswith("/"):
                (media_dir / Path(name).name).write_bytes(package.read(name))
            if (name.startswith("word/header") or name.startswith("word/footer")) and name.endswith(".xml"):
                header_footer_parts[name] = package.read(name).decode("utf-8", errors="ignore")

    (out_dir / "header_footer.xml").write_text(
        json.dumps(header_footer_parts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_manifest(out_dir: Path, manifest: dict[str, Any]) -> None:
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract template-first BUAA DOCX render fragments.")
    parser.add_argument("--template", type=Path, default=ROOT / "templates" / "official" / "buaa_undergraduate_template.docx")
    parser.add_argument("--out", type=Path, default=ROOT / "templates" / "render_fragments")
    args = parser.parse_args(argv)
    manifest = extract_render_fragments(args.template, args.out)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
