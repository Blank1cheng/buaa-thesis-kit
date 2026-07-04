from buaa_thesis_kit.structure_parse import PdfTextLine, parse_pdf_structure


def _line(index: int, text: str, *, page: int = 1, y0: float = 100.0, y1: float = 116.0) -> PdfTextLine:
    return PdfTextLine(
        index=index,
        page=page,
        text=text,
        bbox=(72.0, y0, 520.0, y1),
        page_width=595.0,
        page_height=842.0,
        size=12.0,
        font="SimSun",
    )


def test_parse_pdf_structure_keeps_abstracts_and_toc_out_of_body():
    lines = [
        _line(0, "摘    要", page=3),
        _line(1, "这是中文摘要第一段。", page=3),
        _line(2, "关键词：光电系统，调制传递函数", page=3),
        _line(3, "Abstract", page=4),
        _line(4, "This is the English abstract.", page=4),
        _line(5, "Key Words: electro-optical system, MTF", page=4),
        _line(6, "目       录", page=5),
        _line(7, "1 绪论 1", page=5),
        _line(8, "1.1 课题来源与背景 2", page=5),
        _line(9, "1 绪论", page=6),
        _line(10, "1.1 课题来源与背景", page=6),
        _line(11, "正文第一段。", page=6),
    ]

    parsed = parse_pdf_structure(lines)

    assert parsed.front_matter["chinese_abstract"] == "这是中文摘要第一段。"
    assert parsed.front_matter["keywords_cn"] == "光电系统，调制传递函数"
    assert parsed.front_matter["english_abstract"] == "This is the English abstract."
    assert parsed.front_matter["keywords_en"] == "electro-optical system, MTF"
    assert [section.title for section in parsed.sections] == ["1 绪论", "1.1 课题来源与背景"]
    combined_body = "\n".join(
        "\n".join([section.title, section.text]) for section in parsed.sections
    )
    assert "摘" not in combined_body
    assert "Key Words" not in combined_body
    assert "1 绪论 1" not in combined_body
    assert parsed.removed_toc_line_count == 3


def test_parse_pdf_structure_does_not_promote_chapter_summary_sentence_to_heading():
    parsed = parse_pdf_structure(
        [
            _line(0, "1.5 论文章节安排"),
            _line(1, "论文组织结构如下："),
            _line(2, "第一章 绪论。本章介绍了课题的研究背景和研究意义。"),
            _line(3, "第二章 基于实拍图像的调制传递函数计算方法。本章详细阐述方法。"),
        ]
    )

    assert [section.title for section in parsed.sections] == ["1.5 论文章节安排"]
    assert "第一章 绪论。本章介绍了" in parsed.sections[0].text
    assert "第二章 基于实拍图像" in parsed.sections[0].text


def test_parse_pdf_structure_routes_mergeformat_field_codes_to_equation_review():
    parsed = parse_pdf_structure(
        [
            _line(0, "2.1 性能评估指标"),
            _line(1, "调制传递函数定义如下。"),
            _line(2, r"424 \* MERGEFORMAT"),
            _line(3, "公式章"),
            _line(4, "下一章"),
            _line(5, "公式后正文。"),
        ]
    )

    assert parsed.sections[0].text == "调制传递函数定义如下。\n公式后正文。"
    assert [equation.kind for equation in parsed.equations] == [
        "pdf-field-code",
        "pdf-field-code",
        "pdf-field-code",
    ]
    assert all(equation.requires_review for equation in parsed.equations)
    assert parsed.removed_field_code_line_count == 3


def test_parse_pdf_structure_filters_layout_header_footer_lines():
    parsed = parse_pdf_structure(
        [
            _line(0, "北京航空航天大学毕业设计(论文)", page=8, y0=24.0, y1=36.0),
            _line(1, "第 1 页", page=8, y0=805.0, y1=822.0),
            _line(2, "1 绪论", page=8, y0=120.0, y1=138.0),
            _line(3, "正文内容。", page=8, y0=160.0, y1=178.0),
        ]
    )

    assert [line.text for line in parsed.removed_header_footer_lines] == [
        "北京航空航天大学毕业设计(论文)",
        "第 1 页",
    ]
    assert parsed.sections[0].title == "1 绪论"
    assert parsed.sections[0].text == "正文内容。"
