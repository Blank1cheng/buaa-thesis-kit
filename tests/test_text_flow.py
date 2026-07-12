from buaa_thesis_kit.text_flow import merge_pdf_lines


def test_merge_pdf_lines_combines_chinese_lines_without_spaces():
    paragraphs = merge_pdf_lines(
        [
            "这是中文摘要的第一行",
            "第二行仍然属于同一自然段",
            "",
            "关键词：光电系统，MTF",
        ],
        language="zh",
    )

    assert paragraphs == ["这是中文摘要的第一行第二行仍然属于同一自然段", "关键词：光电系统，MTF"]


def test_merge_pdf_lines_combines_english_lines_with_words_and_hyphenation():
    paragraphs = merge_pdf_lines(
        [
            "This thesis studies perfor-",
            "mance evaluation from images.",
            "",
            "Key Words: optical system, MTF",
        ],
        language="en",
    )

    assert paragraphs == [
        "This thesis studies performance evaluation from images.",
        "Key Words: optical system, MTF",
    ]


def test_merge_pdf_lines_drops_page_headers_and_cover_field_labels():
    paragraphs = merge_pdf_lines(
        [
            "北京航空航天大学毕业设计(论文)",
            "第 I 页",
            "院（系）名称",
            "这是正文内容",
            "继续正文内容",
        ],
        language="zh",
    )

    assert paragraphs == ["这是正文内容继续正文内容"]
