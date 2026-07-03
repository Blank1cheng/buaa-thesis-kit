from pathlib import Path

import fitz

from buaa_thesis_kit.pdf_extract import PdfLine, _extract_metadata, extract_pdf_model


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


def test_extract_metadata_recovers_vertical_cover_lines():
    texts = [
        "单位代码",
        "10006",
        "学",
        "号",
        "20375284",
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
    assert metadata.title_cn == "基于数据驱动的捷联惯性导航组件寿命预测方法研究"
    assert metadata.college == "沈元学院"
    assert metadata.major == "自动化"
    assert metadata.student_name == "宋郭睿"
    assert metadata.advisor == "彭朝琴"
    assert metadata.date == "2024年6月"


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
    assert any("ocr" in warning.lower() for warning in model.extraction_warnings)
