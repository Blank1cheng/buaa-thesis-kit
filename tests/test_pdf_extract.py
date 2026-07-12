import base64
from pathlib import Path

import fitz

from buaa_thesis_kit.pdf_extract import (
    OcrResult,
    PdfLine,
    _extract_content,
    _extract_metadata,
    extract_pdf_model,
)
from buaa_thesis_kit.extract.task_book_extract import extract_task_book_from_blocks
from buaa_thesis_kit.structure_parse import parse_pdf_structure


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _write_text_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    text = "\n".join(
        [
            "Title: PDF Pipeline Thesis",
            "Student Name: Zhang San",
            "Student ID: 20370001",
            "College: Automation College",
            "Major: Automation",
            "Advisor: Li Si",
            "Date: 2026-07",
            "1 Introduction",
            "This PDF contains extractable thesis text.",
            "References",
            "[1] Wang Wu. Test reference. 2026.",
        ]
    )
    page.insert_text((72, 72), text, fontsize=12)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _write_text_pdf_with_captioned_figure(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: PDF Figure Thesis",
                "Student Name: Zhang San",
                "Student ID: 20370001",
                "College: Automation College",
                "Major: Automation",
                "Advisor: Li Si",
                "Date: 2026-07",
                "1 Introduction",
                "This PDF contains body text before a figure.",
            ]
        ),
        fontsize=12,
    )
    page.insert_image(fitz.Rect(80, 48, 116, 84), stream=TINY_PNG)
    page.insert_image(fitz.Rect(120, 220, 340, 350), stream=TINY_PNG)
    page.insert_text((160, 365), "Fig. 1.1 System architecture", fontsize=12)
    page.insert_text((72, 400), "This PDF contains body text after a figure.", fontsize=12)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _write_text_pdf_with_full_page_background_image(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(0, 0, 595, 842), stream=TINY_PNG)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: OCR Layer Thesis",
                "Student Name: Zhang San",
                "Student ID: 20370001",
                "1 Introduction",
                "This PDF has editable text over a scanned page background.",
            ]
        ),
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _write_text_pdf_with_table(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: PDF Table Thesis",
                "Student Name: Zhang San",
                "Student ID: 20370001",
                "College: Automation College",
                "Major: Automation",
                "Advisor: Li Si",
                "Date: 2026-07",
                "1 Introduction",
                "Before table paragraph.",
                "Table 1.1 Evaluation metrics",
                "Metric\tValue",
                "Accuracy\t98%",
                "Recall\t95%",
                "After table paragraph.",
            ]
        ),
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _write_text_pdf_with_equation(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: PDF Equation Thesis",
                "Student Name: Zhang San",
                "Student ID: 20370001",
                "College: Automation College",
                "Major: Automation",
                "Advisor: Li Si",
                "Date: 2026-07",
                "1 Introduction",
                "The state transition model is defined below.",
                "x_k = F x_{k-1} + w_k (2.1)",
                "The equation above is used for prediction.",
            ]
        ),
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _write_text_pdf_with_fraction_equation(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: PDF Fraction Equation Thesis",
                "Student Name: Zhang San",
                "Student ID: 20370001",
                "College: Automation College",
                "Major: Automation",
                "Advisor: Li Si",
                "Date: 2026-07",
                "1 Introduction",
                "The normalized estimate is defined below.",
                r"y = \frac{x_k}{\sqrt{n}} (2.2)",
                "The equation above is used for normalization.",
            ]
        ),
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _write_text_pdf_with_sum_equation(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: PDF Sum Equation Thesis",
                "Student Name: Zhang San",
                "Student ID: 20370001",
                "College: Automation College",
                "Major: Automation",
                "Advisor: Li Si",
                "Date: 2026-07",
                "1 Introduction",
                "The accumulated loss is defined below.",
                r"L = \sum_{i=1}^{n} \alpha_i (3.1)",
                "The equation above is used for loss aggregation.",
            ]
        ),
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _write_text_pdf_with_matrix_equation(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: PDF Matrix Equation Thesis",
                "Student Name: Zhang San",
                "Student ID: 20370001",
                "College: Automation College",
                "Major: Automation",
                "Advisor: Li Si",
                "Date: 2026-07",
                "1 Introduction",
                "The transition matrix is defined below.",
                r"A = \begin{bmatrix} 1 & 0 \\ 0 & 1 \end{bmatrix} (4.1)",
                "The equation above is used for state transition.",
            ]
        ),
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _write_text_pdf_with_cases_equation(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: PDF Cases Equation Thesis",
                "Student Name: Zhang San",
                "Student ID: 20370001",
                "College: Automation College",
                "Major: Automation",
                "Advisor: Li Si",
                "Date: 2026-07",
                "1 Introduction",
                "The piecewise response is defined below.",
                r"f(x) = \begin{cases} x & x > 0 \\ -x & x <= 0 \end{cases} (5.1)",
                "The equation above is used for response clipping.",
            ]
        ),
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _write_blank_pdf(path: Path) -> None:
    document = fitz.open()
    document.new_page(width=300, height=400)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def test_extract_text_pdf_builds_reviewable_thesis_model(tmp_path):
    source = tmp_path / "source.pdf"
    work = tmp_path / "work"
    _write_text_pdf(source)

    model = extract_pdf_model(source, work)

    assert model.status == "needs_review"
    assert model.metadata.title_en == "PDF Pipeline Thesis"
    assert model.metadata.student_name == "Zhang San"
    assert model.metadata.student_id == "20370001"
    assert any("PDF contains extractable thesis text" in section.text for section in model.sections)
    assert any("Test reference" in reference.text for reference in model.references)
    assert any("layout review" in warning.lower() for warning in model.extraction_warnings)


def test_extract_text_pdf_extracts_captioned_figures_and_skips_decorative_images(tmp_path):
    source = tmp_path / "source-with-figure.pdf"
    work = tmp_path / "work"
    _write_text_pdf_with_captioned_figure(source)

    model = extract_pdf_model(source, work)

    assert len(model.figures) == 1
    figure = model.figures[0]
    assert figure.type == "pdf-figure-image"
    assert figure.caption == "Fig. 1.1 System architecture"
    assert Path(figure.path).is_file()
    assert Path(figure.path).suffix == ".png"
    assert figure.requires_review is True
    assert figure.source is not None
    assert figure.source.method == "pdf-embedded-image"
    assert figure.source.page_hint == 1
    assert any("embedded figure" in warning.lower() for warning in model.extraction_warnings)


def test_extract_text_pdf_skips_full_page_background_image_when_text_layer_exists(tmp_path):
    source = tmp_path / "source-with-background.pdf"
    work = tmp_path / "work"
    _write_text_pdf_with_full_page_background_image(source)

    model = extract_pdf_model(source, work)

    assert any("editable text over a scanned page background" in section.text for section in model.sections)
    assert not [figure for figure in model.figures if figure.type == "pdf-figure-image"]


def test_extract_text_pdf_promotes_tabular_rows_to_editable_table(tmp_path):
    source = tmp_path / "source-with-table.pdf"
    work = tmp_path / "work"
    _write_text_pdf_with_table(source)

    model = extract_pdf_model(source, work)

    assert len(model.tables) == 1
    table = model.tables[0]
    assert table.title == "Table 1.1 Evaluation metrics"
    assert table.text == "Metric\tValue\nAccuracy\t98%\nRecall\t95%"
    assert table.source is not None
    assert table.source.method == "pdf-table-text"
    combined_sections = "\n".join(section.text for section in model.sections)
    assert "Before table paragraph." in combined_sections
    assert "After table paragraph." in combined_sections
    assert "Metric\tValue" not in combined_sections
    assert "Accuracy\t98%" not in combined_sections


def test_extract_text_pdf_promotes_stacked_caption_table_to_editable_table(tmp_path):
    source = tmp_path / "stacked-table.pdf"
    work = tmp_path / "work"
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Title: PDF Stacked Table Thesis",
                "Student ID: 20370001",
                "1 Introduction",
                "Table 2.1",
                "FMECA table",
                "Degradation mode",
                "Affected parameter",
                "Optical misalignment",
                "Gyro bias",
                "Table 2.1 analysis lists possible IMU degradation modes.",
            ]
        ),
        fontsize=12,
    )
    document.save(source)
    document.close()

    model = extract_pdf_model(source, work)

    assert len(model.tables) == 1
    assert model.tables[0].title == "Table 2.1 FMECA table"
    assert "Degradation mode" in model.tables[0].text
    assert "Optical misalignment" in model.tables[0].text
    combined_sections = "\n".join(section.text for section in model.sections)
    assert "Table 2.1 analysis" in combined_sections


def _write_pdf_with_positioned_equation_region(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 72), "Title: Positioned Equation Thesis", fontsize=12)
    page.insert_text((72, 100), "Student ID: 20370001", fontsize=12)
    page.insert_text((72, 150), "1 Introduction", fontsize=12)
    page.insert_text((220, 300), "H(0,0)=1", fontsize=14, fontname="tiro")
    page.insert_text((515, 300), "(2-1)", fontsize=12, fontname="tiro")
    page.insert_text((72, 340), "The normalized transfer function is used below.", fontsize=12)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def test_extract_text_pdf_keeps_safe_equation_lines_for_agent_review(tmp_path):
    source = tmp_path / "source-with-equation.pdf"
    work = tmp_path / "work"
    _write_text_pdf_with_equation(source)

    model = extract_pdf_model(source, work)

    assert len(model.equations) == 1
    equation = model.equations[0]
    assert equation.kind == "pdf-text-equation"
    assert equation.text == "x_k = F x_{k-1} + w_k (2.1)"
    assert equation.latex == "x_k = F x_{k-1} + w_k"
    assert equation.number == "(2.1)"
    assert equation.requires_review is True
    assert equation.omml == ""
    assert equation.source is not None
    assert equation.source.method == "pdf-equation-text"
    combined_sections = "\n".join(section.text for section in model.sections)
    assert "x_k = F x_{k-1} + w_k" not in combined_sections
    assert "The equation above is used for prediction." in combined_sections


def test_extract_pdf_locates_number_anchored_equation_region_as_review_image(tmp_path):
    source = tmp_path / "positioned-equation.pdf"
    work = tmp_path / "work"
    _write_pdf_with_positioned_equation_region(source)

    model = extract_pdf_model(source, work)

    assert len(model.equations) == 1
    equation = model.equations[0]
    assert equation.kind == "pdf-image-equation"
    assert equation.number == "(2-1)"
    assert equation.requires_review is True
    assert Path(equation.preview_path).is_file()
    assert len(equation.region_bbox) == 4
    assert equation.region_bbox[2] < 515
    assert equation.source is not None
    assert equation.source.method == "pdf-equation-region"
    assert equation.source.page_hint == 1


def test_extract_text_pdf_keeps_fraction_equations_for_agent_review(tmp_path):
    source = tmp_path / "source-with-fraction-equation.pdf"
    work = tmp_path / "work"
    _write_text_pdf_with_fraction_equation(source)

    model = extract_pdf_model(source, work)

    assert len(model.equations) == 1
    equation = model.equations[0]
    assert equation.kind == "pdf-text-equation"
    assert equation.latex == r"y = \frac{x_k}{\sqrt{n}}"
    assert equation.number == "(2.2)"
    assert equation.requires_review is True
    assert equation.omml == ""
    combined_sections = "\n".join(section.text for section in model.sections)
    assert r"\frac{x_k}{\sqrt{n}}" not in combined_sections
    assert "The equation above is used for normalization." in combined_sections


def test_extract_text_pdf_keeps_sum_and_greek_equations_for_agent_review(tmp_path):
    source = tmp_path / "source-with-sum-equation.pdf"
    work = tmp_path / "work"
    _write_text_pdf_with_sum_equation(source)

    model = extract_pdf_model(source, work)

    assert len(model.equations) == 1
    equation = model.equations[0]
    assert equation.latex == r"L = \sum_{i=1}^{n} \alpha_i"
    assert equation.number == "(3.1)"
    assert equation.requires_review is True
    assert equation.omml == ""
    combined_sections = "\n".join(section.text for section in model.sections)
    assert r"\sum_{i=1}^{n}" not in combined_sections
    assert "The equation above is used for loss aggregation." in combined_sections


def test_extract_text_pdf_keeps_matrix_equations_for_agent_review(tmp_path):
    source = tmp_path / "source-with-matrix-equation.pdf"
    work = tmp_path / "work"
    _write_text_pdf_with_matrix_equation(source)

    model = extract_pdf_model(source, work)

    assert len(model.equations) == 1
    equation = model.equations[0]
    assert equation.latex == r"A = \begin{bmatrix} 1 & 0 \\ 0 & 1 \end{bmatrix}"
    assert equation.number == "(4.1)"
    assert equation.requires_review is True
    assert equation.omml == ""
    combined_sections = "\n".join(section.text for section in model.sections)
    assert r"\begin{bmatrix}" not in combined_sections
    assert "The equation above is used for state transition." in combined_sections


def test_extract_text_pdf_keeps_cases_equations_for_agent_review(tmp_path):
    source = tmp_path / "source-with-cases-equation.pdf"
    work = tmp_path / "work"
    _write_text_pdf_with_cases_equation(source)

    model = extract_pdf_model(source, work)

    assert len(model.equations) == 1
    equation = model.equations[0]
    assert equation.latex == r"f(x) = \begin{cases} x & x > 0 \\ -x & x <= 0 \end{cases}"
    assert equation.number == "(5.1)"
    assert equation.requires_review is True
    assert equation.omml == ""
    combined_sections = "\n".join(section.text for section in model.sections)
    assert r"\begin{cases}" not in combined_sections
    assert "The equation above is used for response clipping." in combined_sections


def test_extract_metadata_recovers_vertical_cover_lines():
    texts = [
        "单位代码",
        "10006",
        "学",
        "号",
        "20375284",
        "1 分类号",
        "TN953",
        "毕业设计(论文)",
        "基于数据驱动的捷联惯性导航组件",
        "寿命预测方法研究",
        "学",
        "院",
        "名",
        "称",
        "沈元学院",
        "专",
        "业",
        "名",
        "称",
        "自动化",
        "学",
        "生",
        "姓",
        "名",
        "宋郭睿",
        "指",
        "导",
        "教",
        "师",
        "彭朝琴",
        "2024 年6 月",
    ]
    lines = [PdfLine(index=index, page=1, text=text) for index, text in enumerate(texts)]

    metadata = _extract_metadata(lines)

    assert metadata.unit_code == "10006"
    assert metadata.student_id == "20375284"
    assert metadata.classification == "TN953"
    assert metadata.title_cn == "基于数据驱动的捷联惯性导航组件寿命预测方法研究"
    assert metadata.college == "沈元学院"
    assert metadata.major == "自动化"
    assert metadata.student_name == "宋郭睿"
    assert metadata.advisor == "彭朝琴"
    assert metadata.date == "2024年6月"


def test_extract_metadata_stops_title_at_horizontal_college_label():
    texts = [
        "单位代码",
        "10006",
        "学",
        "号",
        "17375303",
        "分类号",
        "TP273",
        "毕业设计(论文)",
        "基于实拍图像的光电系统性能评估",
        "关键技术研究",
        "院（系）名称",
        "自动化科学与电气工程学院",
        "专",
        "业",
        "名",
        "称",
        "自动化",
        "学",
        "生",
        "姓",
        "名",
        "崔润昊",
        "指",
        "导",
        "教",
        "师",
        "唐荻音",
        "2021 年5 月",
    ]
    lines = [PdfLine(index=index, page=1, text=text) for index, text in enumerate(texts)]

    metadata = _extract_metadata(lines)

    assert metadata.title_cn == "基于实拍图像的光电系统性能评估关键技术研究"
    assert metadata.college == "自动化科学与电气工程学院"
    assert metadata.evidence["college"].method == "pdf-next-line-label"


def test_extract_metadata_attaches_high_confidence_pdf_cover_evidence():
    texts = [
        "单位代码",
        "10006",
        "学",
        "号",
        "20375284",
        "1 分类号",
        "TN953",
        "毕业设计(论文)",
        "基于数据驱动的捷联惯性导航组件",
        "寿命预测方法研究",
        "学",
        "院",
        "名",
        "称",
        "沈元学院",
        "专",
        "业",
        "名",
        "称",
        "自动化",
        "学",
        "生",
        "姓",
        "名",
        "宋郭睿",
        "指",
        "导",
        "教",
        "师",
        "彭朝琴",
        "2024 年6 月",
    ]
    lines = [PdfLine(index=index, page=1, text=text) for index, text in enumerate(texts)]

    metadata = _extract_metadata(lines)

    for field in ("unit_code", "student_id", "classification", "title_cn", "college", "major", "student_name", "advisor", "date"):
        evidence = metadata.evidence[field]
        assert evidence.confidence >= 0.75
        assert evidence.evidence_text
        assert evidence.source_type == "pdf"


def test_parse_pdf_structure_skips_buaa_cover_and_spine_before_body():
    texts = [
        (1, "单位代码"),
        (1, "10006"),
        (1, "学"),
        (1, "号"),
        (1, "20375284"),
        (1, "1 分类号"),
        (1, "TN953"),
        (1, "毕业设计(论文)"),
        (1, "基于数据驱动的捷联惯性导航组件"),
        (1, "寿命预测方法研究"),
        (1, "2024 年6 月"),
        (2, "论文封面书脊"),
        (2, "四号黑体字"),
        (2, "北"),
        (2, "京"),
        (2, "航"),
        (2, "空"),
        (2, "航"),
        (2, "天"),
        (2, "大"),
        (2, "学"),
        (3, "北京航空航天大学"),
        (3, "本科生毕业设计（论文）任务书"),
        (3, "Ⅰ、毕业设计（论文）题目："),
        (3, "基于数据驱动的捷联惯性导航组件寿命预测方法研究"),
        (5, "摘"),
        (5, "要"),
        (5, "摘要内容。"),
        (8, "1"),
        (8, "绪论"),
        (8, "1.1 课题来源"),
        (8, "正文内容。"),
    ]
    lines = [
        PdfLine(index=index, page=page, text=text)
        for index, (page, text) in enumerate(texts)
    ]

    parsed = parse_pdf_structure(lines)
    combined = "\n".join([section.title + "\n" + section.text for section in parsed.sections])

    assert "分类号" not in combined
    assert "论文封面书脊" not in combined
    assert "四号黑体字" not in combined
    assert "1 绪论" in [section.title for section in parsed.sections]
    assert "正文内容。" in combined


def test_parse_pdf_structure_rejects_formula_fragments_as_headings():
    lines = [
        PdfLine(index=0, page=1, text="2.2 基于Simulink 的IMU 仿真模型构建"),
        PdfLine(index=1, page=1, text="正文内容。"),
        PdfLine(index=2, page=2, text="2 + �1"),
        PdfLine(index=3, page=2, text="2 ∆��(��)��"),
        PdfLine(index=4, page=2, text="(2.13)"),
        PdfLine(index=5, page=3, text="2.3 数据仿真及退化注入"),
        PdfLine(index=6, page=3, text="后续正文。"),
    ]

    parsed = parse_pdf_structure(lines)
    titles = [section.title for section in parsed.sections]
    combined = "\n".join([section.title + "\n" + section.text for section in parsed.sections])

    assert "2 + �1" not in titles
    assert "2 ∆��(��)��" not in titles
    assert "2.2 基于Simulink 的IMU 仿真模型构建" in titles
    assert "2.3 数据仿真及退化注入" in titles
    assert "(2.13)" in combined


def test_parse_pdf_structure_rejects_layout_math_and_body_fragments_as_headings():
    width = 595.3
    height = 841.9
    lines = [
        PdfLine(
            index=0,
            page=1,
            text="2021 年5 月",
            bbox=(266.6, 698.8, 354.7, 719.0),
            size=15.0,
            page_width=width,
            page_height=height,
        ),
        PdfLine(
            index=1,
            page=10,
            text="1.1 课题来源与背景",
            bbox=(85.1, 156.9, 190.1, 173.0),
            size=12.0,
            page_width=width,
            page_height=height,
        ),
        PdfLine(index=2, page=10, text="正文内容。", page_width=width, page_height=height),
        PdfLine(
            index=3,
            page=22,
            text="1 y 卷积",
            bbox=(489.5, 117.7, 538.6, 133.7),
            size=11.9,
            page_width=width,
            page_height=height,
        ),
        PdfLine(index=4, page=22, text="公式后的正文。", page_width=width, page_height=height),
        PdfLine(
            index=5,
            page=26,
            text="2",
            bbox=(277.5, 537.3, 281.0, 546.6),
            size=6.9,
            font="TimesNewRomanPSMT",
            page_width=width,
            page_height=height,
        ),
        PdfLine(
            index=6,
            page=26,
            text="det",
            bbox=(131.7, 545.9, 140.1, 555.1),
            size=6.9,
            font="TimesNewRomanPSMT",
            page_width=width,
            page_height=height,
        ),
        PdfLine(index=7, page=26, text="继续正文。", page_width=width, page_height=height),
        PdfLine(
            index=8,
            page=31,
            text="3.8.1 上运行，调用opencv-python、numpy、scipy、matplotlib、pylsd-nova 等扩展包，输",
            bbox=(85.1, 399.7, 538.6, 415.8),
            size=12.0,
            page_width=width,
            page_height=height,
        ),
        PdfLine(
            index=9,
            page=39,
            text="3.11 所示。",
            bbox=(85.1, 672.2, 144.6, 688.3),
            size=12.0,
            page_width=width,
            page_height=height,
        ),
        PdfLine(
            index=10,
            page=66,
            text="5.1 需求性分析",
            bbox=(85.1, 309.1, 166.1, 325.2),
            size=12.0,
            page_width=width,
            page_height=height,
        ),
        PdfLine(index=11, page=66, text="后续正文。", page_width=width, page_height=height),
    ]

    parsed = parse_pdf_structure(lines)
    titles = [section.title for section in parsed.sections]
    combined = "\n".join(section.text for section in parsed.sections)

    assert titles == ["1.1 课题来源与背景", "5.1 需求性分析"]
    assert "公式后的正文。" in combined
    assert "2 det" not in titles
    assert "继续正文。" in combined
    assert "3.8.1 上运行" in combined
    assert "3.11 所示。" in combined


def test_extract_content_skips_buaa_cover_and_spine_but_keeps_task_book():
    texts = [
        (1, "单位代码"),
        (1, "10006"),
        (1, "学"),
        (1, "号"),
        (1, "20375284"),
        (1, "1 分类号"),
        (1, "TN953"),
        (1, "毕业设计(论文)"),
        (1, "基于数据驱动的捷联惯性导航组件"),
        (1, "寿命预测方法研究"),
        (1, "2024 年6 月"),
        (2, "论文封面书脊"),
        (2, "四号黑体字"),
        (2, "基"),
        (2, "于"),
        (2, "宋"),
        (2, "郭"),
        (2, "睿"),
        (2, "北京航空航天大学"),
        (3, "北京航空航天大学"),
        (3, "本科生毕业设计（论文）任务书"),
        (3, "Ⅰ、毕业设计（论文）题目："),
        (3, "基于数据驱动的捷联惯性导航组件寿命预测方法研究"),
        (4, "摘 要"),
        (4, "这是摘要内容。"),
        (8, "1 绪论"),
        (8, "这是正文内容。"),
    ]
    lines = [
        PdfLine(index=index, page=page, text=text)
        for index, (page, text) in enumerate(texts)
    ]

    sections, _references = _extract_content(lines)
    combined = "\n".join([section.title + "\n" + section.text for section in sections])

    assert "20375284" not in combined
    assert "论文封面书脊" not in combined
    assert "四号黑体字" not in combined
    assert "本科生毕业设计（论文）任务书" in combined
    assert "这是正文内容。" in combined


def test_pdf_task_book_lines_extract_raw_materials_work_content_and_references():
    texts = [
        (3, "北京航空航天大学"),
        (3, "本科生毕业设计（论文）任务书"),
        (3, "Ⅰ、毕业设计（论文）题目："),
        (3, "基于数据驱动的捷联惯性导航组件寿命预测方法研究"),
        (3, "Ⅱ、毕业设计（论文）使用的原始资料（数据）及设计技术要求："),
        (3, "实验室具有计算机硬件以及python 软件开发平台。"),
        (3, "该毕业设计要求基于数据驱动的方法，完成惯组组件的寿命预测。"),
        (3, "Ⅲ、毕业设计（论文）工作内容："),
        (3, "1、惯组组件仿真模型搭建；"),
        (3, "2、完成激光陀螺寿命预测方法的研究；"),
        (4, "Ⅳ、主要参考资料："),
        (4, "[1] 陈自强."),
        (4, "基于LSTM 网络的设备健康状况评估与剩余寿命预测方法的研究[D].中国科学技术大学,2019."),
        (4, "指导教师：彭朝琴"),
        (5, "本人声明"),
    ]
    lines = [PdfLine(index=index, page=page, text=text) for index, (page, text) in enumerate(texts)]

    task = extract_task_book_from_blocks(lines, {"advisor": "彭朝琴"})

    assert "计算机硬件" in task["raw_materials"]
    assert "寿命预测" in task["raw_materials"]
    assert "惯组组件仿真模型搭建" in task["work_content"]
    assert "激光陀螺寿命预测" in task["work_content"]
    assert task["references"][0]["raw"].startswith("[1] 陈自强.")
    assert task["advisor"] == "彭朝琴"
    assert task["missing_fields"] == []


def test_extract_content_splits_front_matter_and_skips_toc_entries():
    declaration = "\u672c\u4eba\u58f0\u660e"
    chinese_abstract = "\u6458\u8981"
    toc = "\u76ee\u5f55"
    introduction = "1 \u7eea\u8bba"
    topic_source = "1.1 \u8bfe\u9898\u6765\u6e90"
    lines = [
        PdfLine(index=0, page=3, text="\u5317\u4eac\u822a\u7a7a\u822a\u5929\u5927\u5b66"),
        PdfLine(index=1, page=3, text="\u672c\u79d1\u751f\u6bd5\u4e1a\u8bbe\u8ba1\uff08\u8bba\u6587\uff09\u4efb\u52a1\u4e66"),
        PdfLine(index=2, page=3, text="\u4efb\u52a1\u4e66\u5185\u5bb9"),
        PdfLine(index=3, page=4, text=declaration),
        PdfLine(index=4, page=4, text="\u58f0\u660e\u5185\u5bb9"),
        PdfLine(index=5, page=5, text="Student preamble that belongs to abstract page"),
        PdfLine(index=6, page=5, text="\u6458"),
        PdfLine(index=7, page=5, text="\u8981"),
        PdfLine(index=8, page=5, text="\u4e2d\u6587\u6458\u8981\u5185\u5bb9"),
        PdfLine(index=9, page=6, text="Research on data-driven thesis title"),
        PdfLine(index=10, page=6, text="Author : Zhang San"),
        PdfLine(index=11, page=6, text="Tutor : Li Si"),
        PdfLine(index=12, page=6, text="Abstract"),
        PdfLine(index=13, page=6, text="English abstract body."),
        PdfLine(index=14, page=7, text="\u76ee"),
        PdfLine(index=15, page=7, text="\u5f55"),
        PdfLine(index=16, page=7, text=f"{introduction}...................................................................... 1"),
        PdfLine(index=17, page=7, text=f"{topic_source}........................................................1"),
        PdfLine(index=18, page=7, text="2.2.1"),
        PdfLine(index=19, page=7, text="Split TOC continuation................................................18"),
        PdfLine(index=20, page=8, text="1"),
        PdfLine(index=21, page=8, text="\u7eea\u8bba"),
        PdfLine(index=22, page=8, text=topic_source),
        PdfLine(index=23, page=8, text="\u6b63\u6587\u5185\u5bb9"),
    ]

    sections, _references = _extract_content(lines)
    titles = [section.title for section in sections]
    combined = "\n".join([section.title + "\n" + section.text for section in sections])

    assert declaration in titles
    assert chinese_abstract in titles
    assert "Abstract" in titles
    assert introduction in titles
    assert topic_source in titles
    assert toc not in combined
    declaration_section = next(section for section in sections if section.title == declaration)
    cn_abstract_section = next(section for section in sections if section.title == chinese_abstract)
    assert "Student preamble" not in declaration_section.text
    assert "Research on data-driven" not in cn_abstract_section.text
    assert "Author :" not in cn_abstract_section.text
    assert "Tutor :" not in cn_abstract_section.text
    assert "Split TOC continuation" not in combined
    assert "................................................................" not in combined


def test_extract_content_filters_pdf_running_headers_and_page_number_fragments():
    lines = [
        PdfLine(index=0, page=1, text="北京航空航天大学毕业设计(论文)"),
        PdfLine(index=1, page=1, text="第"),
        PdfLine(index=2, page=1, text="页"),
        PdfLine(index=3, page=1, text="I"),
        PdfLine(index=4, page=1, text="摘要"),
        PdfLine(index=5, page=1, text="摘要正文。"),
        PdfLine(index=6, page=2, text="北京航空航天大学毕业设计(论文)"),
        PdfLine(index=7, page=2, text="第"),
        PdfLine(index=8, page=2, text="10"),
        PdfLine(index=9, page=2, text="页"),
        PdfLine(index=10, page=2, text="1 绪论"),
        PdfLine(index=11, page=2, text="正文内容。"),
    ]

    sections, _references = _extract_content(lines)
    combined = "\n".join([section.title + "\n" + section.text for section in sections])

    assert "北京航空航天大学毕业设计(论文)" not in combined
    assert "\n第\n" not in f"\n{combined}\n"
    assert "\n页\n" not in f"\n{combined}\n"
    assert "\nI\n" not in f"\n{combined}\n"
    assert "\n10\n" not in f"\n{combined}\n"
    assert "摘要正文。" in combined
    assert "正文内容。" in combined


def test_extract_blank_pdf_renders_page_image_and_marks_ocr_review(tmp_path):
    source = tmp_path / "blank.pdf"
    work = tmp_path / "work"
    _write_blank_pdf(source)

    model = extract_pdf_model(source, work)

    assert model.status == "needs_review"
    assert len(model.figures) == 1
    assert Path(model.figures[0].path).is_file()
    assert model.figures[0].path.endswith(".png")
    assert model.figures[0].requires_review is True
    assert len(model.ocr_ledger) == 1
    assert model.ocr_ledger[0].page == 1
    assert model.ocr_ledger[0].status == "needs_ocr"
    assert model.ocr_ledger[0].image_path.endswith("pdf-page-001.png")
    assert model.ocr_ledger[0].confidence == 0.0
    assert model.ocr_ledger[0].requires_review is True
    assert any("ocr" in warning.lower() for warning in model.extraction_warnings)


def test_extract_scanned_pdf_uses_ocr_text_as_editable_sections(tmp_path):
    source = tmp_path / "scanned.pdf"
    work = tmp_path / "work"
    _write_blank_pdf(source)

    def fake_ocr(image_path: Path) -> OcrResult:
        assert image_path.name == "pdf-page-001.png"
        return OcrResult(
            text="1 Introduction\nOCR recovered editable body text.",
            confidence=0.86,
            engine="fake-ocr",
        )

    model = extract_pdf_model(source, work, ocr_engine=fake_ocr)

    assert model.status == "needs_review"
    assert len(model.figures) == 1
    assert Path(model.figures[0].path).is_file()
    assert len(model.ocr_ledger) == 1
    assert model.ocr_ledger[0].status == "ocr_text_extracted"
    assert model.ocr_ledger[0].text_characters == len("1 Introduction\nOCR recovered editable body text.")
    assert model.ocr_ledger[0].confidence == 0.86
    assert model.ocr_ledger[0].requires_review is True
    assert model.ocr_ledger[0].source is not None
    assert model.ocr_ledger[0].source.method == "fake-ocr"
    assert any("OCR recovered editable body text." in section.text for section in model.sections)
