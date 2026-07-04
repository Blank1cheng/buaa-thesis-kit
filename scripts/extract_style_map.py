from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
DEFAULT_OUTPUT = ROOT / "templates" / "official" / "style_map.json"


def extract_style_map(template_path: Path, output_path: Path = DEFAULT_OUTPUT) -> dict[str, str]:
    """Extract semantic thesis style ids from the official template's styles.xml."""
    template = Path(template_path)
    styles = _load_styles(template)
    style_map = {
        "chapter": _first_existing(styles, ("Heading1", "1", "Title1"), names=("heading 1", "标题 1")),
        "section": _first_existing(styles, ("Heading2", "2", "Title2"), names=("heading 2", "标题 2")),
        "subsection": _first_existing(styles, ("Heading3", "3", "Title3"), names=("heading 3", "标题 3")),
        "body": _first_existing(styles, ("Normal",), names=("normal", "正文")),
        "caption_figure": _first_existing(styles, ("Caption", "FigureCaption"), names=("caption", "题注", "图题")),
        "caption_table": _first_existing(styles, ("Caption", "TableCaption"), names=("caption", "题注", "表题")),
        "toc1": _first_existing(styles, ("TOC1",), names=("toc 1", "目录 1")),
        "toc2": _first_existing(styles, ("TOC2",), names=("toc 2", "目录 2")),
        "toc3": _first_existing(styles, ("TOC3",), names=("toc 3", "目录 3")),
        "reference": _first_existing(styles, ("Reference", "Normal"), names=("reference", "参考文献", "normal")),
        "acknowledgement": _first_existing(styles, ("Normal",), names=("normal", "正文")),
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(style_map, ensure_ascii=False, indent=2), encoding="utf-8")
    return style_map


def _load_styles(template_path: Path) -> dict[str, dict[str, Any]]:
    with zipfile.ZipFile(template_path) as package:
        styles_xml = package.read("word/styles.xml")
    root = etree.fromstring(styles_xml)
    styles: dict[str, dict[str, Any]] = {}
    for style in root.findall("w:style", NS):
        style_id = style.get(f"{{{W_NS}}}styleId")
        if not style_id:
            continue
        name_node = style.find("w:name", NS)
        name = name_node.get(f"{{{W_NS}}}val") if name_node is not None else ""
        styles[style_id] = {"name": name or ""}
    return styles


def _first_existing(styles: dict[str, dict[str, Any]], ids: tuple[str, ...], names: tuple[str, ...]) -> str:
    for style_id in ids:
        if style_id in styles:
            return style_id
    lowered_names = {name.lower() for name in names}
    for style_id, style in styles.items():
        if style.get("name", "").lower() in lowered_names:
            return style_id
    return ids[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract semantic style ids from official BUAA template.")
    parser.add_argument("--template", type=Path, default=ROOT / "templates" / "official" / "buaa_undergraduate_template.docx")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    style_map = extract_style_map(args.template, args.out)
    print(json.dumps(style_map, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

