from __future__ import annotations

from buaa_thesis_kit.extract.metadata_extract import resolve_metadata_from_texts


def test_extracts_spaced_and_colon_labels_with_evidence():
    report = resolve_metadata_from_texts(
        [
            {"text": "单位代码 10006", "paragraph_index": 0, "source_region": "cover"},
            {"text": "学    号      17375303", "paragraph_index": 1, "source_region": "cover"},
            {"text": "分 类 号    TP273", "paragraph_index": 2, "source_region": "cover"},
            {"text": "学生姓名：崔润昊", "paragraph_index": 3, "source_region": "cover"},
            {"text": "指导教师：唐荫韬", "paragraph_index": 4, "source_region": "cover"},
            {"text": "学院：自动化科学与电气工程学院", "paragraph_index": 5, "source_region": "cover"},
            {"text": "专业/班级：自动化", "paragraph_index": 6, "source_region": "cover"},
        ],
        source_file="source.docx",
        source_type="docx",
    )

    assert report["resolved"]["unit_code"]["value"] == "10006"
    assert report["resolved"]["student_id"]["value"] == "17375303"
    assert report["resolved"]["classification"]["value"] == "TP273"
    assert report["resolved"]["student_name"]["value"] == "崔润昊"
    assert report["resolved"]["advisor"]["value"] == "唐荫韬"
    assert report["resolved"]["college"]["value"] == "自动化科学与电气工程学院"
    assert report["resolved"]["major"]["value"] == "自动化"
    assert report["resolved"]["student_name"]["evidence"] == "学生姓名：崔润昊"
    assert report["resolved"]["student_name"]["confidence"] >= 0.9


def test_extracts_cover_position_fields_when_template_labels_are_missing():
    report = resolve_metadata_from_texts(
        [
            {"text": "单位代码 10006", "paragraph_index": 0, "source_region": "cover"},
            {"text": "学 号 17375303", "paragraph_index": 1, "source_region": "cover"},
            {"text": "分类号 TP273", "paragraph_index": 2, "source_region": "cover"},
            {"text": "基于实拍图像的光电系统性能评估关键技术研究", "paragraph_index": 3, "source_region": "cover"},
            {"text": "自动化科学与电气工程学院", "paragraph_index": 4, "source_region": "cover"},
            {"text": "自动化", "paragraph_index": 5, "source_region": "cover"},
            {"text": "崔润昊", "paragraph_index": 6, "source_region": "cover"},
            {"text": "唐荫韬", "paragraph_index": 7, "source_region": "cover"},
            {"text": "2021 年 5 月", "paragraph_index": 8, "source_region": "cover"},
        ],
        source_file="source.docx",
        source_type="docx",
    )

    resolved = report["resolved"]
    assert resolved["title_cn"]["value"] == "基于实拍图像的光电系统性能评估关键技术研究"
    assert resolved["college"]["value"] == "自动化科学与电气工程学院"
    assert resolved["major"]["value"] == "自动化"
    assert resolved["student_name"]["value"] == "崔润昊"
    assert resolved["advisor"]["value"] == "唐荫韬"
    assert resolved["date"]["value"] == "2021 年 5 月"
    assert resolved["college"]["rule"] == "cover_position"


def test_reports_conflicting_high_confidence_candidates():
    report = resolve_metadata_from_texts(
        [
            {"text": "学生姓名：张三", "paragraph_index": 0, "source_region": "cover"},
            {"text": "作者：李四", "paragraph_index": 1, "source_region": "abstract_cn"},
        ],
        source_file="source.docx",
        source_type="docx",
    )

    assert report["resolved"]["student_name"]["value"] == "张三"
    assert report["conflicts"]
    assert report["conflicts"][0]["field"] == "student_name"


def test_does_not_resolve_official_template_sample_values():
    report = resolve_metadata_from_texts(
        [
            {"text": "学生姓名：王小二", "paragraph_index": 0, "source_region": "cover"},
            {"text": "指导教师：黄欢", "paragraph_index": 1, "source_region": "cover"},
        ],
        source_file="source.docx",
        source_type="docx",
    )

    assert "student_name" not in report["resolved"]
    assert "advisor" not in report["resolved"]
    assert "student_name" in report["missing"]


def test_english_abstract_author_tutor_do_not_conflict_with_chinese_metadata():
    report = resolve_metadata_from_texts(
        [
            {"text": "学生姓名：崔润昊", "paragraph_index": 0, "source_region": "cover"},
            {"text": "指导教师：唐荻音", "paragraph_index": 1, "source_region": "cover"},
            {"text": "Author: CUI Run-hao", "paragraph_index": 55, "source_region": "body"},
            {"text": "Tutor: TANG Di-yin", "paragraph_index": 56, "source_region": "body"},
        ],
        source_file="source.docx",
        source_type="docx",
    )

    assert report["resolved"]["student_name"]["value"] == "崔润昊"
    assert report["resolved"]["advisor"]["value"] == "唐荻音"
    assert not report["conflicts"]
    assert all(candidate["value"] not in {"CUI", "TANG"} for candidate in report["candidates"])


def test_taskbook_footer_college_major_class_line_does_not_override_college():
    report = resolve_metadata_from_texts(
        [
            {"text": "学院：自动化科学与电气工程学院", "paragraph_index": 0, "source_region": "cover"},
            {"text": "自动化科学与电气工程 学院 自动化 专业类 170325 班", "paragraph_index": 35, "source_region": "frontmatter"},
        ],
        source_file="source.docx",
        source_type="docx",
    )

    assert report["resolved"]["college"]["value"] == "自动化科学与电气工程学院"
    assert not report["conflicts"]
    assert len([candidate for candidate in report["candidates"] if candidate["field"] == "college"]) == 1


def test_taskbook_date_range_does_not_conflict_with_completion_date():
    report = resolve_metadata_from_texts(
        [
            {"text": "2021年5月", "paragraph_index": 14, "source_region": "frontmatter"},
            {"text": "毕业设计（论文）时间： 2020 年 12 月 31 日至 2021 年 5月 23 日", "paragraph_index": 37, "source_region": "frontmatter"},
            {"text": "时间：2021年 5 月", "paragraph_index": 47, "source_region": "body"},
        ],
        source_file="source.docx",
        source_type="docx",
    )

    assert report["resolved"]["date"]["value"] == "2021 年 5 月"
    assert not report["conflicts"]
    assert all("2020 年 12 月 31 日" not in candidate["value"] for candidate in report["candidates"])
