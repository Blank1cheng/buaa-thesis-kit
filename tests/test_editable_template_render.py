import zipfile
from pathlib import Path

from docx import Document

from buaa_thesis_kit.editable_template_render import render_editable_buaa_docx
from buaa_thesis_kit.models import ContentBlock, EquationItem, Metadata, ThesisModel


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "buaa_undergraduate_thesis_template.docx"
OMML_FRAGMENT = (
    '<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
    "<m:oMath><m:r><m:t>x+y</m:t></m:r></m:oMath>"
    "</m:oMathPara>"
)


def test_render_editable_buaa_docx_reuses_template_without_page_screenshots(tmp_path):
    model = ThesisModel(
        metadata=Metadata(
            title_cn="Editable Template Thesis",
            student_name="Zhang San",
            student_id="20370001",
            college="Automation College",
            major="Automation",
            advisor="Li Si",
            date="2026年7月",
            classification="TN953",
        ),
        sections=[
            ContentBlock(
                id="body-1",
                type="section",
                title="1 Introduction",
                text="Editable body paragraph from the extracted source.",
                level=1,
            )
        ],
        references=[
            ContentBlock(
                id="ref-1",
                type="reference",
                text="[1] Wang Wu. Editable template test. 2026.",
            )
        ],
        status="needs_review",
    )
    output = tmp_path / "thesis.docx"

    render_editable_buaa_docx(TEMPLATE, model, output)

    document = Document(str(output))
    visible_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Editable Template Thesis" in visible_text
    assert "20370001" in visible_text
    assert "Editable body paragraph from the extracted source." in visible_text
    assert "书脊" in visible_text
    assert "PDF Extracted Text" not in visible_text

    with zipfile.ZipFile(output) as docx_zip:
        document_xml = docx_zip.read("word/document.xml").decode("utf-8")
        media_names = [name for name in docx_zip.namelist() if name.startswith("word/media/")]

    assert '<w:br w:type="page"' in document_xml
    assert "Micro-process of Oil/Water" not in document_xml
    assert not any("pdf-page" in name for name in media_names)


def test_render_editable_buaa_docx_compacts_cover_spacing_for_long_titles(tmp_path):
    model = ThesisModel(
        metadata=Metadata(
            title_cn="基于数据驱动的捷联惯性导航组件寿命预测方法研究",
            student_name="宋郭睿",
            student_id="20375284",
            college="沈元学院",
            major="自动化",
            advisor="彭朝琴",
            date="2024年6月",
            classification="TN953",
        ),
        sections=[ContentBlock(id="body-1", type="section", text="正文内容。")],
    )
    output = tmp_path / "long-title.docx"

    render_editable_buaa_docx(TEMPLATE, model, output)

    document = Document(str(output))
    before_spine = []
    for paragraph in document.paragraphs:
        if paragraph.text.strip() == "书脊":
            break
        before_spine.append(paragraph.text)

    blank_cover_paragraphs = [text for text in before_spine if not text.strip()]
    assert "2024年6月" in before_spine
    assert len(blank_cover_paragraphs) <= 7


def test_render_editable_buaa_docx_shrinks_long_cover_table_values(tmp_path):
    model = ThesisModel(
        metadata=Metadata(
            title_cn="基于实拍图像的光电系统性能评估关键技术研究",
            student_name="崔润昊",
            student_id="17375303",
            college="自动化科学与电气工程学院",
            major="自动化",
            advisor="唐荻音",
            date="2021年5月",
            classification="TP273",
        ),
        sections=[ContentBlock(id="body-1", type="section", text="正文内容。")],
    )
    output = tmp_path / "long-cover-table-value.docx"

    render_editable_buaa_docx(TEMPLATE, model, output)

    document = Document(str(output))
    college_cell = document.tables[0].rows[0].cells[1]
    sizes = [
        run.font.size.pt
        for paragraph in college_cell.paragraphs
        for run in paragraph.runs
        if run.font.size is not None
    ]
    assert college_cell.text == "自动化科学与电气工程学院"
    assert sizes
    assert max(sizes) <= 12


def test_render_editable_buaa_docx_preserves_omml_equations_as_word_math(tmp_path):
    model = ThesisModel(
        metadata=Metadata(
            title_cn="Equation Template Thesis",
            student_name="Zhang San",
            student_id="20370001",
            college="Automation College",
            major="Automation",
            advisor="Li Si",
            date="2026-06",
            classification="TP273",
        ),
        sections=[ContentBlock(id="body-1", type="section", text="Body text.")],
        equations=[
            EquationItem(
                id="eq-omml",
                kind="omml",
                text="x+y",
                omml=OMML_FRAGMENT,
                requires_review=True,
            )
        ],
    )
    output = tmp_path / "omml-equation.docx"

    render_editable_buaa_docx(TEMPLATE, model, output)

    with zipfile.ZipFile(output) as docx_zip:
        document_xml = docx_zip.read("word/document.xml").decode("utf-8")
    assert "<m:oMathPara" in document_xml
    assert "<m:t>x+y</m:t>" in document_xml
    assert "[Equation requires review]" not in document_xml


def test_render_editable_buaa_docx_starts_front_matter_sections_on_new_pages(tmp_path):
    declaration = "\u672c\u4eba\u58f0\u660e"
    chinese_abstract = "\u6458\u8981"
    model = ThesisModel(
        metadata=Metadata(
            title_cn="Paged Front Matter Thesis",
            student_name="Zhang San",
            student_id="20370001",
            college="Automation College",
            major="Automation",
            advisor="Li Si",
            date="2026-06",
            classification="TP273",
        ),
        sections=[
            ContentBlock(id="task", type="section", title="", text="Task book body."),
            ContentBlock(id="declare", type="section", title=declaration, text="Declaration body."),
            ContentBlock(id="abstract-cn", type="section", title=chinese_abstract, text="Chinese abstract body."),
            ContentBlock(id="body", type="chapter", title="1 Introduction", text="Body text.", level=1),
        ],
    )
    output = tmp_path / "front-matter-pages.docx"

    render_editable_buaa_docx(TEMPLATE, model, output)

    document = Document(str(output))
    paragraphs = list(document.paragraphs)
    paragraph_texts = [paragraph.text for paragraph in paragraphs]
    for marker in (declaration, chinese_abstract, "1 Introduction"):
        index = paragraph_texts.index(marker)
        previous_xml = paragraphs[index - 1]._p.xml
        assert '<w:br w:type="page"' in previous_xml
