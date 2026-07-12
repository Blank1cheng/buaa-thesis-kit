import json
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest


DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
</Types>
"""

PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdHeader1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
  <Relationship Id="rIdFooter1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
  <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/></w:style>
  <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/></w:style>
  <w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/></w:style>
</w:styles>
"""

NUMBERING_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0"/>
</w:numbering>
"""

HEADER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:r><w:t>{{STUDENT_NAME}}</w:t></w:r></w:p>
</w:hdr>
"""

FOOTER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText>PAGE</w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>
</w:ftr>
"""

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02\x00\x00\x00\x0bIDATx\xdac\xfc\xff"
    b"\x1f\x00\x03\x03\x02\x00\xef\xbf\xa7\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _paragraph(text: str = "", style: str | None = None, extra: str = "") -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    run = f"<w:r><w:t>{escape(text)}</w:t></w:r>" if text else ""
    return f"<w:p>{ppr}{run}{extra}</w:p>"


def _minimal_docx(path: Path) -> None:
    cover = "\u6bd5\u4e1a\u8bbe\u8ba1(\u8bba\u6587)"
    spine = "\u8bba\u6587\u5c01\u9762\u4e66\u810a"
    task = "\u672c\u79d1\u6bd5\u4e1a\u8bbe\u8ba1\uff08\u8bba\u6587\uff09\u4efb\u52a1\u4e66"
    declaration = "\u672c\u4eba\u58f0\u660e"
    abstract_cn = "\u6458    \u8981"
    toc = "\u76ee    \u5f55"
    chapter = "1 \u7eea\u8bba"
    figure = "\u56fe1.1 \u793a\u4f8b\u56fe"
    table = "\u88681.1 \u793a\u4f8b\u8868"
    acknowledgement = "\u81f4\u8c22"
    references = "\u53c2\u8003\u6587\u732e"
    appendix = "\u9644\u5f55"
    toc_field = (
        '<w:fldSimple w:instr="TOC \\o &quot;1-3&quot; \\h \\z \\u">'
        "<w:r><w:t>TOC field placeholder</w:t></w:r>"
        "</w:fldSimple>"
    )
    textbox = (
        "<w:r><w:pict><v:shape xmlns:v=\"urn:schemas-microsoft-com:vml\">"
        "<v:textbox><w:txbxContent>"
        "<w:p><w:r><w:t>{{BOX_VALUE}}</w:t></w:r></w:p>"
        "</w:txbxContent></v:textbox></v:shape></w:pict></w:r>"
    )
    sect_pr = (
        '<w:sectPr><w:headerReference w:type="default" r:id="rIdHeader1"/>'
        '<w:footerReference w:type="default" r:id="rIdFooter1"/>'
        '<w:pgNumType w:fmt="decimal" w:start="1"/></w:sectPr>'
    )
    body = "".join(
        [
            _paragraph(cover),
            _paragraph("{{TI", extra="<w:r><w:t>TLE_CN}}</w:t></w:r>"),
            _paragraph(spine),
            _paragraph(task),
            _paragraph(declaration),
            _paragraph(abstract_cn),
            _paragraph("Abstract"),
            _paragraph(toc, extra=toc_field),
            _paragraph(chapter, style="Heading1"),
            _paragraph("1.1 \u7814\u7a76\u80cc\u666f", style="Heading2"),
            _paragraph("\u6b63\u6587\u6bb5\u843d\u3002"),
            _paragraph(figure, style="Caption", extra=textbox),
            _paragraph(table, style="Caption"),
            _paragraph(acknowledgement, style="Heading1"),
            _paragraph(references, style="Heading1"),
            _paragraph(appendix, style="Heading1"),
        ]
    )
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:v="urn:schemas-microsoft-com:vml">
  <w:body>{body}{sect_pr}</w:body>
</w:document>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", DOCX_CONTENT_TYPES)
        package.writestr("_rels/.rels", PACKAGE_RELS)
        package.writestr("word/document.xml", document_xml)
        package.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        package.writestr("word/styles.xml", STYLES_XML)
        package.writestr("word/numbering.xml", NUMBERING_XML)
        package.writestr("word/header1.xml", HEADER_XML)
        package.writestr("word/footer1.xml", FOOTER_XML)
        package.writestr("word/media/image1.png", TINY_PNG)


def _docx_xml(path: Path, part: str = "word/document.xml") -> str:
    with zipfile.ZipFile(path) as package:
        return package.read(part).decode("utf-8")


def _docx_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as package:
        return set(package.namelist())


def _rewrite_docx_part(path: Path, part: str, data: str) -> None:
    temp_path = path.with_suffix(".rewrite.docx")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            target.writestr(item, data.encode("utf-8") if item.filename == part else source.read(item.filename))
    temp_path.replace(path)


def test_prepare_official_template_copies_docx_and_records_manifest(tmp_path):
    from scripts.prepare_official_template import prepare_official_template

    source = tmp_path / "official-source.docx"
    target = tmp_path / "templates" / "official" / "buaa_undergraduate_template.docx"
    _minimal_docx(source)

    result = prepare_official_template(source, target)

    assert result["status"] == "pass"
    assert result["conversion_method"] == "copy_docx"
    assert target.exists()
    assert zipfile.is_zipfile(target)
    manifest = json.loads((target.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["output"] == str(target)
    assert manifest["preserved_parts"]["styles"] is True
    assert manifest["preserved_parts"]["header_footer"] is True
    assert manifest["preserved_parts"]["relationships"] is True
    assert manifest["preserved_parts"]["media"] is True


def test_prepare_official_template_uses_converter_for_legacy_doc(tmp_path, monkeypatch):
    import scripts.prepare_official_template as module

    legacy_doc = tmp_path / "official-source.doc"
    target = tmp_path / "templates" / "official" / "buaa_undergraduate_template.docx"
    converted_fixture = tmp_path / "converted.docx"
    legacy_doc.write_bytes(b"legacy word bytes")
    _minimal_docx(converted_fixture)
    calls = []

    def fake_convert(source: Path, output: Path):
        calls.append((source, output))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(converted_fixture.read_bytes())
        return True, "DOC to DOCX converted with Word COM"

    monkeypatch.setattr(module, "convert_doc_to_docx", fake_convert)

    result = module.prepare_official_template(legacy_doc, target)

    assert result["status"] == "pass"
    assert result["conversion_method"] == "word_convert"
    assert calls == [(legacy_doc, target)]
    assert zipfile.is_zipfile(target)


def test_replace_docx_placeholders_handles_split_runs_headers_and_textboxes(tmp_path):
    from buaa_thesis_kit.template_engine.placeholder_replace import replace_docx_placeholders

    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _minimal_docx(source)

    replace_docx_placeholders(
        source,
        output,
        {
            "TITLE_CN": "\u57fa\u4e8e\u6a21\u677f\u7684\u8bba\u6587",
            "STUDENT_NAME": "\u5f20\u4e09",
            "BOX_VALUE": "\u6587\u672c\u6846\u5185\u5bb9",
        },
    )

    document_xml = _docx_xml(output)
    header_xml = _docx_xml(output, "word/header1.xml")
    assert "{{" not in document_xml
    assert "{{" not in header_xml
    assert "\u57fa\u4e8e\u6a21\u677f\u7684\u8bba\u6587" in document_xml
    assert "\u6587\u672c\u6846\u5185\u5bb9" in document_xml
    assert "\u5f20\u4e09" in header_xml


def test_template_engine_ooxml_helpers_preserve_package_parts(tmp_path):
    from buaa_thesis_kit.template_engine.fragment_loader import load_package_parts
    from buaa_thesis_kit.template_engine.fragment_merger import write_package_with_replaced_parts
    from buaa_thesis_kit.template_engine.media_importer import media_parts
    from buaa_thesis_kit.template_engine.rels_importer import relationship_parts
    from buaa_thesis_kit.template_engine.section_manager import extract_last_section_properties
    from buaa_thesis_kit.template_engine.style_importer import style_parts

    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _minimal_docx(source)

    parts = load_package_parts(source)
    assert "word/document.xml" in parts
    assert "word/styles.xml" in style_parts(parts)
    assert "word/numbering.xml" in style_parts(parts)
    assert "word/_rels/document.xml.rels" in relationship_parts(parts)
    assert "word/media/image1.png" in media_parts(parts)
    assert b"<w:sectPr" in extract_last_section_properties(parts["word/document.xml"])

    replacement_xml = parts["word/document.xml"].replace(b"{{TI", b"{{REPLACED_TI")
    write_package_with_replaced_parts(source, output, {"word/document.xml": replacement_xml})

    assert zipfile.is_zipfile(output)
    assert "{{REPLACED_TI" in _docx_xml(output)
    assert "word/media/image1.png" in _docx_names(output)


def test_extract_render_fragments_preserves_official_ooxml_parts(tmp_path):
    from scripts.extract_render_fragments import REQUIRED_FRAGMENTS, extract_render_fragments

    source = tmp_path / "official.docx"
    out_dir = tmp_path / "templates" / "render_fragments"
    _minimal_docx(source)

    result = extract_render_fragments(source, out_dir)

    assert result["status"] == "pass"
    for fragment in REQUIRED_FRAGMENTS:
        path = out_dir / f"{fragment}.docx"
        assert path.exists(), fragment
        assert zipfile.is_zipfile(path), fragment
        names = _docx_names(path)
        assert "word/document.xml" in names
        assert "word/styles.xml" in names
        assert "word/numbering.xml" in names
        assert "word/_rels/document.xml.rels" in names

    assert (out_dir / "styles.xml").exists()
    assert (out_dir / "numbering.xml").exists()
    assert (out_dir / "relationships" / "document.xml.rels").exists()
    assert (out_dir / "media" / "image1.png").exists()
    assert "word/media/image1.png" in _docx_names(out_dir / "cover.docx")
    assert "TOC" in _docx_xml(out_dir / "toc.docx")
    body_xml = _docx_xml(out_dir / "body_base.docx")
    assert "{{BODY}}" in body_xml
    assert "<w:sectPr" in body_xml
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == str(source)
    assert manifest["fragments"]["cover"]["source"] == "official_template"
    assert manifest["fragments"]["body_base"]["status"] == "pass"


def test_extract_render_fragments_reports_missing_anchors_without_silent_fallback(tmp_path):
    from scripts.extract_render_fragments import extract_render_fragments

    source = tmp_path / "official.docx"
    out_dir = tmp_path / "fragments"
    _minimal_docx(source)
    broken_xml = _docx_xml(source).replace("\u672c\u4eba\u58f0\u660e", "missing declaration")
    _rewrite_docx_part(source, "word/document.xml", broken_xml)

    result = extract_render_fragments(source, out_dir)

    assert result["status"] == "needs_review"
    assert "declaration" in result["missing_fragments"]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["fragments"]["declaration"]["status"] == "missing_anchor"


def test_extract_render_fragments_detects_non_11_figure_and_table_captions(tmp_path):
    from scripts.extract_render_fragments import extract_render_fragments

    source = tmp_path / "official.docx"
    out_dir = tmp_path / "fragments"
    _minimal_docx(source)
    updated_xml = (
        _docx_xml(source)
        .replace("\u56fe1.1 \u793a\u4f8b\u56fe", "\u56fe3.1  \u90e8\u5206\u76f8\u5e72\u89e3\u8c03")
        .replace("\u88681.1 \u793a\u4f8b\u8868", "\u88683.1 \u65b9\u6cd5\u2014\u5e72\u6270\u6291\u5236\u7ed3\u679c")
    )
    _rewrite_docx_part(source, "word/document.xml", updated_xml)

    result = extract_render_fragments(source, out_dir)

    assert result["status"] == "pass"
    assert result["fragments"]["body_figure_block"]["status"] == "pass"
    assert result["fragments"]["body_table_block"]["status"] == "pass"


def test_extract_render_fragments_prefers_caption_start_over_inline_figure_mentions(tmp_path):
    from scripts.extract_render_fragments import extract_render_fragments

    source = tmp_path / "official.docx"
    out_dir = tmp_path / "fragments"
    _minimal_docx(source)
    figure_para = _paragraph("\u56fe1.1 \u793a\u4f8b\u56fe", style="Caption", extra=(
        "<w:r><w:pict><v:shape xmlns:v=\"urn:schemas-microsoft-com:vml\">"
        "<v:textbox><w:txbxContent>"
        "<w:p><w:r><w:t>{{BOX_VALUE}}</w:t></w:r></w:p>"
        "</w:txbxContent></v:textbox></v:shape></w:pict></w:r>"
    ))
    note_para = _paragraph("\u6ce8\uff1a\u6b64\u56fe\u4e2d\u7684\u66f2\u7ebf\u4e0e\u56fe2.1\u76f8\u540c\u3002")
    xml = _docx_xml(source).replace(figure_para, note_para + figure_para)
    _rewrite_docx_part(source, "word/document.xml", xml)

    result = extract_render_fragments(source, out_dir)

    assert result["status"] == "pass"
    figure_xml = _docx_xml(out_dir / "body_figure_block.docx")
    assert "\u56fe1.1" in figure_xml
    assert "\u6ce8\uff1a" not in figure_xml


def test_extract_render_fragments_skips_manual_toc_entries_and_synthesizes_toc_field(tmp_path):
    from scripts.extract_render_fragments import extract_render_fragments

    source = tmp_path / "official.docx"
    out_dir = tmp_path / "fragments"
    _minimal_docx(source)
    xml = _docx_xml(source)
    xml = re.sub(r"<w:fldSimple[^>]*>.*?</w:fldSimple>", "", xml)
    toc_marker = "<w:r><w:t>\u76ee    \u5f55</w:t></w:r>"
    toc_end = xml.index("</w:p>", xml.index(toc_marker)) + len("</w:p>")
    manual_toc_entries = "".join(
        [
            _paragraph("1 \u7eea\u8bba\u2026\u2026\u2026\u20261"),
            _paragraph("\u81f4\u8c22\u2026\u2026\u2026\u202654"),
            _paragraph("\u53c2\u8003\u6587\u732e\u2026\u202655"),
            _paragraph("\u9644\u5f55\u2026\u2026\u202656"),
            _paragraph("TOC1"),
            _paragraph("1"),
        ]
    )
    _rewrite_docx_part(source, "word/document.xml", xml[:toc_end] + manual_toc_entries + xml[toc_end:])

    result = extract_render_fragments(source, out_dir)

    assert result["status"] == "pass"
    assert "TOC" in _docx_xml(out_dir / "toc.docx")
    assert "\u7eea\u8bba\u2026" not in _docx_xml(out_dir / "body_chapter_start.docx")
    assert "\u53c2\u8003\u6587\u732e\u2026" not in _docx_xml(out_dir / "references.docx")
    assert "\u81f4\u8c22\u2026" not in _docx_xml(out_dir / "acknowledgement.docx")
    assert "\u9644\u5f55\u2026" not in _docx_xml(out_dir / "appendix.docx")


def test_extract_render_fragments_derives_acknowledgement_from_official_heading_style(tmp_path):
    from scripts.extract_render_fragments import extract_render_fragments

    source = tmp_path / "official.docx"
    out_dir = tmp_path / "fragments"
    _minimal_docx(source)
    xml = _docx_xml(source).replace(_paragraph("\u81f4\u8c22", style="Heading1"), "")
    _rewrite_docx_part(source, "word/document.xml", xml)

    result = extract_render_fragments(source, out_dir)

    assert result["status"] == "pass"
    assert result["fragments"]["acknowledgement"]["status"] == "derived_from_official_body_style"
    acknowledgement_xml = _docx_xml(out_dir / "acknowledgement.docx")
    assert "\u81f4\u8c22" in acknowledgement_xml
    assert "{{ACKNOWLEDGEMENT}}" in acknowledgement_xml


def test_extract_style_map_uses_actual_template_style_ids(tmp_path):
    from scripts.extract_style_map import extract_style_map

    source = tmp_path / "official.docx"
    output = tmp_path / "style_map.json"
    _minimal_docx(source)

    style_map = extract_style_map(source, output)

    assert style_map["chapter"] == "Heading1"
    assert style_map["section"] == "Heading2"
    assert style_map["subsection"] == "Heading3"
    assert style_map["body"] == "Normal"
    assert style_map["caption_figure"] == "Caption"
    assert style_map["toc1"] == "TOC1"
    assert json.loads(output.read_text(encoding="utf-8")) == style_map
