import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from buaa_thesis_kit.models import ContentBlock, Metadata, ThesisModel


DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
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
</Relationships>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="a"><w:name w:val="正文"/></w:style>
  <w:style w:type="paragraph" w:styleId="1"><w:name w:val="标题 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="2"><w:name w:val="标题 2"/></w:style>
  <w:style w:type="paragraph" w:styleId="3"><w:name w:val="标题 3"/></w:style>
  <w:style w:type="paragraph" w:styleId="af0"><w:name w:val="题注"/></w:style>
</w:styles>
"""

NUMBERING_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0"/>
</w:numbering>
"""

HEADER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:r><w:t>北京航空航天大学毕业设计(论文)</w:t></w:r></w:p>
</w:hdr>
"""

FOOTER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText>PAGE</w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>
</w:ftr>
"""


def _paragraph(text: str = "", style: str | None = None, extra: str = "") -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    run = f"<w:r><w:t>{escape(text)}</w:t></w:r>" if text else ""
    return f"<w:p>{ppr}{run}{extra}</w:p>"


def _table_cell(text: str) -> str:
    return (
        "<w:tbl><w:tr><w:tc><w:tcPr><w:tcW w:type=\"auto\"/></w:tcPr>"
        f"{_paragraph(text)}"
        "</w:tc></w:tr></w:tbl>"
    )


def _write_official_like_docx(path: Path) -> None:
    toc_field = (
        '<w:fldSimple w:instr="TOC \\o &quot;1-3&quot; \\h \\z \\u">'
        "<w:r><w:t>目录域</w:t></w:r>"
        "</w:fldSimple>"
    )
    body = "".join(
        [
            _paragraph("单位代码       10006"),
            _paragraph("学    号     38020326"),
            _paragraph("分类号    TN953"),
            _paragraph("毕业设计(论文)"),
            _paragraph("（题目）"),
            _paragraph("学院名称"),
            _table_cell("电子信息工程学院"),
            _paragraph("专业名称"),
            _table_cell("电子与信息技术"),
            _paragraph("学生姓名"),
            _table_cell("李兴新"),
            _paragraph("指导教师"),
            _table_cell("毛  峡"),
            _paragraph("2015年6月"),
            _paragraph("论文题目姓名北京航空航天大学"),
            _paragraph("本科生毕业设计（论文）任务书"),
            _paragraph("Ⅰ、毕业设计（论文）题目："),
            _paragraph("Ⅱ、毕业设计（论文）使用的原始资料（数据）及设计技术要求："),
            _paragraph("Ⅲ、毕业设计（论文）工作内容："),
            _paragraph("Ⅳ、主要参考资料："),
            _paragraph("学院（系）             专业类              班"),
            _paragraph("学生"),
            _paragraph("毕业设计（论文）时间：        年   月   日至      年    月    日"),
            _paragraph("答辩时间：        年    月    日"),
            _paragraph("成    绩："),
            _paragraph("指导教师："),
            _paragraph("系（教研室） 主任（签字）："),
            _paragraph("本人声明"),
            _paragraph("作者：王小亮"),
            _paragraph("时间：2015年 6 月"),
            _paragraph("油/水电迁移微观动态过程的研究"),
            _paragraph("学生：黄  欣"),
            _paragraph("指导教师：朱岳麟"),
            _paragraph("摘    要"),
            _table_cell("电分离工艺技术在炼油工业中是效率最好、最经济的油/水分离方法。"),
            _paragraph("关键词：高频高压，油/水电迁移"),
            _paragraph("Micro-process of Oil/Water Transferring in Electric Field"),
            _paragraph("Author : HUANG Xin"),
            _paragraph("Tutor : ZHU Yue-lin"),
            _paragraph("Abstract"),
            _table_cell("Electro-desalting is the most efficient and the most economical oil/water separation method desalting."),
            _paragraph("Key words：High-frequency high-voltage"),
            _paragraph("目       录", extra=toc_field),
            _paragraph("1 绪论……………………1"),
            _paragraph("参考文献………………55"),
            _paragraph("3  I级叶/盘转子错频方案的对比分析", style="1"),
            _paragraph("模板正文示例段落。", style="a"),
            _paragraph("3.5  多自由度系统的强迫响应分析", style="2"),
            _paragraph("参考文献", style="1"),
            _paragraph("毛峡, 丁玉宽. 图像的情感特征分析[J].", style="a"),
        ]
    )
    sect_pr = (
        '<w:sectPr><w:headerReference w:type="default" r:id="rIdHeader1"/>'
        '<w:footerReference w:type="default" r:id="rIdFooter1"/>'
        '<w:pgNumType w:fmt="decimal" w:start="1"/></w:sectPr>'
    )
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
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


def _part(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as package:
        return package.read(name)


def _document_xml(path: Path) -> str:
    return _part(path, "word/document.xml").decode("utf-8")


def _package_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as package:
        return set(package.namelist())


def _sample_model() -> ThesisModel:
    return ThesisModel(
        metadata=Metadata(
            title_cn="基于实拍图像的光电系统性能评估关键技术研究",
            title_en="Performance Evaluation of Electro-Optical Systems",
            student_name="张三",
            student_id="20370001",
            college="自动化科学与电气工程学院",
            major="自动化",
            advisor="李四",
            date="2026年6月",
            classification="TP273",
            unit_code="10006",
        ),
        front_matter={
            "chinese_abstract": "这是中文摘要第一段。\n这是中文摘要第二段。",
            "keywords_cn": "光电系统，性能评估",
            "english_abstract": "This is the English abstract.",
            "keywords_en": "electro-optical system, performance evaluation",
            "author_en": "ZHANG San",
            "tutor_en": "LI Si",
        },
        sections=[
            ContentBlock(id="ch1", type="chapter", title="1 绪论", text="正文自然段。", level=1),
            ContentBlock(id="sec11", type="section", title="1.1 研究背景", text="背景段落。", level=2),
        ],
        references=[ContentBlock(id="ref1", type="reference", text="[1] 王五. 测试文献[J]. 2026.")],
    )


def test_instrument_official_template_marks_original_package_in_place(tmp_path):
    from scripts.instrument_official_template import instrument_official_template

    source = tmp_path / "official.docx"
    target = tmp_path / "official.instrumented.docx"
    _write_official_like_docx(source)

    report = instrument_official_template(source, target)

    assert report["status"] == "pass"
    assert target.exists()
    assert _part(source, "word/styles.xml") == _part(target, "word/styles.xml")
    assert _part(source, "word/numbering.xml") == _part(target, "word/numbering.xml")
    assert _part(source, "word/header1.xml") == _part(target, "word/header1.xml")
    xml = _document_xml(target)
    for marker in (
        "{{UNIT_CODE}}",
        "{{STUDENT_ID}}",
        "{{COLLEGE}}",
        "{{MAJOR}}",
        "{{TITLE_CN_LINE1}}",
        "{{SPINE_TITLE_CN}}",
        "{{TASK_TITLE}}",
        "{{TASK_COLLEGE_MAJOR_CLASS}}",
        "{{TASK_DATE_RANGE}}",
        "{{TASK_DEFENSE_DATE}}",
        "{{TASK_GRADE}}",
        "{{TASK_DIRECTOR_SIGNATURE}}",
        "{{DECLARATION_STUDENT_NAME}}",
        "{{ABSTRACT_CN}}",
        "{{ABSTRACT_EN}}",
        "{{BODY_START}}",
        "{{BODY_END}}",
        "{{REFERENCES}}",
    ):
        assert marker in xml
    assert "Ⅰ、毕业设计（论文）题目：{{TASK_TITLE}}TOC" not in xml
    assert "李兴新" not in xml
    assert "毛  峡" not in xml
    assert "fldSimple" in xml and "TOC" in xml
    manifest = json.loads((target.parent / "instrument_manifest.json").read_text(encoding="utf-8"))
    assert manifest["created_from"] == str(source)
    assert manifest["output"] == str(target)


def test_assemble_in_place_copies_base_and_replaces_inside_existing_template(tmp_path):
    from buaa_thesis_kit.assemble_in_place import assemble_in_place
    from scripts.instrument_official_template import instrument_official_template

    official = tmp_path / "official.docx"
    base = tmp_path / "official.instrumented.docx"
    output = tmp_path / "output" / "thesis.docx"
    _write_official_like_docx(official)
    instrument_official_template(official, base)

    report = assemble_in_place(base, _sample_model(), output)

    assert report["created_by_copying_base"] is True
    assert report["fragment_merge_used"] is False
    assert report["frontmatter_generated_by_add_paragraph"] is False
    assert _part(base, "word/styles.xml") == _part(output, "word/styles.xml")
    assert _part(base, "word/numbering.xml") == _part(output, "word/numbering.xml")
    assert _part(base, "word/header1.xml") == _part(output, "word/header1.xml")
    xml = _document_xml(output)
    assert "基于实拍图像的光电系统性能评估" in xml
    assert "关键技术研究" in xml
    assert "20370001" in xml
    assert "这是中文摘要第一段。" in xml
    assert "This is the English abstract." in xml
    assert "1 绪论" in xml
    assert "正文自然段。" in xml
    assert "[1] 王五. 测试文献[J]. 2026." in xml
    assert "模板正文示例段落" not in xml
    assert "{{" not in xml
    assert "北京航空航天大学毕业设计(论文)" not in xml
    assert _package_names(base) == _package_names(output)


def test_validate_template_inheritance_reports_template_breakage(tmp_path):
    from buaa_thesis_kit.assemble_in_place import assemble_in_place
    from scripts.instrument_official_template import instrument_official_template
    from scripts.validate_template_inheritance import validate_template_inheritance

    official = tmp_path / "official.docx"
    base = tmp_path / "official.instrumented.docx"
    candidate = tmp_path / "output" / "thesis.docx"
    report_path = tmp_path / "output" / "template_inheritance_report.json"
    _write_official_like_docx(official)
    instrument_official_template(official, base)
    assemble_in_place(base, _sample_model(), candidate)

    report = validate_template_inheritance(base, candidate, report_path)

    assert report["status"] == "pass"
    assert report["created_by_copying_base"] is True
    assert report["styles_xml_changed"] is False
    assert report["numbering_xml_changed"] is False
    assert report["toc_field_exists"] is True
    assert report["page_number_fields_exist"] is True
    assert report["header_footer_as_body_text"] is False
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "pass"

    broken = tmp_path / "output" / "broken.docx"
    with zipfile.ZipFile(candidate) as src, zipfile.ZipFile(broken, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/styles.xml":
                data = data.replace(b"paragraph", b"changedxx")
            dst.writestr(item, data)

    broken_report = validate_template_inheritance(base, broken)

    assert broken_report["status"] == "failed"
    assert broken_report["styles_xml_changed"] is True
