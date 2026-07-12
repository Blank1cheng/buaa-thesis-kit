from __future__ import annotations

import re
from pathlib import Path

from buaa_thesis_kit.extract.metadata_normalize import normalize_metadata
from buaa_thesis_kit.extract.reference_extract import merge_reference_entries, normalize_reference_items
from buaa_thesis_kit.extract.task_book_extract import extract_task_book_from_blocks
from buaa_thesis_kit.latex import render_buaa as latex_renderer
from buaa_thesis_kit.latex.pipeline import _latex_model_from_thesis_model, _write_latex_gate_reports
from buaa_thesis_kit.latex.render_buaa import (
    _assign,
    _assign_patch,
    _assignment_text_lines,
    _com_info,
    _cover_title_lines,
    _display_width,
    _figure_block,
    _main_undergraduate,
    _references,
    _reflow_pdf_paragraphs,
    _task_book_report,
    render_buaa_latex,
)
from tests.test_buaa_latex_pipeline import _fake_buaa_template


class _Block:
    def __init__(self, index: int, text: str) -> None:
        self.index = index
        self.text = text


def _without_cjk_breaks(value: str) -> str:
    return value.replace(r"\allowbreak{}", "")


def test_taskbook_date_range_and_blank_defense_date_are_rendered_verbatim():
    model = {
        "metadata": {"date": "2021 年 5 月"},
        "task_book": {
            "date_range": "2020 年 12 月 31 日至 2021 年 5 月 23 日",
            "defense_date": "2021 年 月 日",
        },
        "abstract_cn": {},
        "abstract_en": {},
    }

    tex = _com_info(model, "undergraduate")

    assert r"\thesisbegin{2020}{12}{31}" in tex
    assert r"\thesisend{2021}{5}{23}" in tex
    assert r"\defense{2021}{}{}" in tex


def test_taskbook_report_records_date_source_without_fallback():
    report = _task_book_report(
        {
            "task_book": {
                "date_range": "2020 年 12 月 31 日至 2021 年 5 月 23 日",
                "defense_date": "2021 年 月 日",
            }
        }
    )

    assert report["date_range"] == "2020 年 12 月 31 日至 2021 年 5 月 23 日"
    assert report["defense_date"] == "2021 年 月 日"
    assert report["date_fallback_fields"] == []


def test_taskbook_technical_text_is_not_hard_wrapped_in_python():
    text = (
        "第一段短文本。\n"
        "第二段包含足够多的中文和 MTF English words so XeLaTeX must choose the line breaks."
    )

    tex = _assign({"task_book": {"raw_materials": text, "work_content": "（1）工作内容"}})
    normalized_tex = _without_cjk_breaks(tex)

    assert r"\buaaAssignTextParagraph{第一段短文本。}" in normalized_tex
    assert (
        r"\buaaAssignTextParagraph{第二段包含足够多的中文和 MTF English words so XeLaTeX must choose the line breaks.}"
        in normalized_tex
    )
    assert r"\buaaAssignTextLine" not in tex


def test_pdf_physical_lines_are_reflowed_before_latex_rendering():
    paragraphs = _reflow_pdf_paragraphs(
        "捷联惯性导航系统的核心组件——惯\n"
        "性测量单元负责提供精确位置、速度和姿态\n"
        "信息。\n"
        "1. 建立 IMU 仿真模型，并完成验证。"
    )

    assert paragraphs == [
        "捷联惯性导航系统的核心组件——惯性测量单元负责提供精确位置、速度和姿态信息。",
        "1. 建立 IMU 仿真模型，并完成验证。",
    ]


def test_pdf_english_line_wraps_are_joined_and_soft_hyphens_repaired():
    paragraphs = _reflow_pdf_paragraphs(
        "Traditional maintenance strategies are unable to meet advanced applica-\n"
        "tion requirements.\n"
        "2. Health indicator construction uses CNN and LSTM."
    )

    assert paragraphs == [
        "Traditional maintenance strategies are unable to meet advanced application requirements.",
        "2. Health indicator construction uses CNN and LSTM.",
    ]


def test_pdf_taskbook_requirements_use_semantic_paragraphs_not_source_lines():
    tex = _assign(
        {
            "source_type": "pdf",
            "task_book": {
                "raw_materials": "第一行因 PDF 版宽断开\n后半行应继续自然排版。",
                "work_content": "1、第一项内容\n2、第二项内容",
            },
        }
    )

    raw_block = tex.split(r"\newcommand{\buaaAssignReqBlock}", 1)[1].split(
        r"\newcommand{\buaaAssignWorkBlock}", 1
    )[0]
    assert raw_block.count(r"\buaaAssignTextParagraph") == 1
    raw_block_without_breaks = _without_cjk_breaks(raw_block)
    assert "第一行因" in raw_block_without_breaks and "后半行" in raw_block_without_breaks


def test_taskbook_reference_style_is_small_four_one_point_five_without_hanging_indent():
    patch = _assign_patch({"metadata": {}, "task_book": {}})

    assert r"\zihao{-4}" in patch
    assert r"\begin{spacing}{1.5}" in patch
    assert r"\hangindent" not in patch
    assert r"\buaaAssignRefParagraph" in patch


def test_taskbook_underlined_paragraphs_do_not_put_hfill_inside_uline():
    patch = _assign_patch({"metadata": {}, "task_book": {}})

    assert r"\uline{#1}" in patch
    assert r"\uline{#1\hfill}" not in patch


def test_taskbook_cjk_text_adds_break_opportunities_without_fixed_line_breaks():
    tex = _assign({"task_book": {"raw_materials": "本毕设使用中文文本并保留 MTF words。"}})

    assert r"本\allowbreak{}毕\allowbreak{}设" in tex
    assert r"\\" not in tex.split(r"\buaaAssignTextParagraph", 1)[1].splitlines()[0]


def test_taskbook_reference_adds_break_opportunities_at_spaces_and_hyphens():
    tex = _assign(
        {
            "task_book": {
                "references": [
                    {"raw": "[1] Electronic Still Picture Imaging-Resolution and Spatial Frequency Responses[M]."}
                ]
            }
        }
    )

    assert r"Picture \allowbreak{}Imaging-\allowbreak{}Resolution" in tex


def test_undergraduate_main_is_monochrome_and_loads_spine_template():
    tex = _main_undergraduate()

    assert "oneside,color," not in tex
    assert r"\include{data/bachelor/spine}" in tex


def test_spine_template_uses_model_title_author_and_school():
    tex = latex_renderer._spine_tex(
        {
            "metadata": {
                "title_cn": "基于实拍图像的光电系统性能评估关键技术研究",
                "student_name": "崔润昊",
            }
        }
    )

    assert r"\newcommand{\buaaSpinePage}" in tex
    assert r"基\\于\\实\\拍" in tex
    assert r"崔\\润\\昊" in tex
    assert r"北\\京\\航\\空\\航\\天\\大\\学" in tex
    assert r"\patchcmd{\maketitle}{\titlech}{\titlech\buaaSpinePage}" in tex


def test_extract_task_book_sections_references_and_fallback_fields():
    blocks = [
        _Block(18, "本科毕业设计（论文）任务书"),
        _Block(19, "Ⅰ、毕业设计（论文）题目："),
        _Block(20, "基于实拍图像的光电系统性能评估关键技术研究"),
        _Block(21, "Ⅱ、毕业设计（论文）使用的原始资料（数据）及设计技术要求："),
        _Block(22, "本毕设的原始数据来源于中国知网，IEEE等网络论文数据库。"),
        _Block(23, "设计算法通过光电系统拍摄的图像实现MTF的自动计算。"),
        _Block(24, "Ⅲ、毕业设计（论文）工作内容："),
        _Block(25, "（1）基于图像计算MTF的python编程实现"),
        _Block(26, "（2）自动目标区域提取算法的设计"),
        _Block(29, "Ⅳ、主要参考资料："),
        _Block(30, "[1] 张建奇. 红外系统[M]. 西安电子科技大学出版社, 2018."),
        _Block(31, "西安: 236."),
        _Block(32, "[2] Boreman G D. Modulation transfer function[M]. SPIE press, 2001."),
        _Block(35, "自动化科学与电气工程 学院 自动化 专业类 170325 班"),
        _Block(36, "学生 崔润昊"),
        _Block(37, "毕业设计（论文）时间： 2020 年 12 月 31 日至 2021 年 5月 23 日"),
        _Block(40, "指导教师： 唐荻音"),
        _Block(43, "本人声明"),
    ]
    metadata = {
        "college": "自动化科学与电气工程学院",
        "major": "自动化",
        "student_name": "崔润昊",
        "advisor": "唐荻音",
    }

    task = extract_task_book_from_blocks(blocks, metadata)

    assert task["title"] == "基于实拍图像的光电系统性能评估关键技术研究"
    assert "中国知网" in task["raw_materials"]
    assert "自动目标区域提取算法" in task["work_content"]
    assert [item["raw"] for item in task["references"]] == [
        "[1] 张建奇. 红外系统[M]. 西安电子科技大学出版社, 2018. 西安: 236.",
        "[2] Boreman G D. Modulation transfer function[M]. SPIE press, 2001.",
    ]
    assert task["college"] == "自动化科学与电气工程学院"
    assert task["major"] == "自动化"
    assert task["major_class"] == "自动化"
    assert task["class_name"] == "170325"
    assert task["student_name"] == "崔润昊"
    assert task["advisor"] == "唐荻音"


def test_reference_continuation_lines_are_merged_without_cross_region_leak():
    entries = merge_reference_entries(
        [
            "[1] Tang D, Gong M. System-level performance prediction",
            "for infrared systems[J]. IEEE Transactions, 2021.",
            "[2] 王娜. 红外成像系统性能评估关键问题研究[D].",
            "西安电子科技大学, 2009.",
            "指导教师： 唐荻音",
        ],
        stop_predicate=lambda line: line.startswith("指导教师"),
    )

    assert entries == [
        "[1] Tang D, Gong M. System-level performance prediction for infrared systems[J]. IEEE Transactions, 2021.",
        "[2] 王娜. 红外成像系统性能评估关键问题研究[D]. 西安电子科技大学, 2009.",
    ]


def test_reference_merge_repairs_english_spacing_and_splits_joined_entries():
    entries = merge_reference_entries(
        [
            "[1] 张建奇. 红外系统[M]. 西安电子科技大学出版社: 西安,2018:236 [2] Sonka M, Hlavac V,BoyleR. 艾海舟, 苏延超译[M].",
            "图像处理, 分析与机器视觉(第三版), 2011: 86-102.",
        ]
    )

    assert len(entries) == 2
    assert entries[0].startswith("[1] 张建奇")
    assert "Hlavac V, Boyle R. 艾海舟" in entries[1]
    assert "V,Boyle" not in entries[1]
    assert "BoyleR" not in entries[1]
    assert not any("[1]" in entry and "[2]" in entry for entry in entries)


def test_reference_issue_number_is_not_split_into_a_new_reference():
    items = normalize_reference_items(
        [
            {
                "raw": "[4] 吴魁，王仙勇，孙洁，等. 基于深度学习的故障检测方法[J]. "
                "计算机测量与控制，2017，25（010）：43-47."
            }
        ]
    )

    assert len(items) == 1
    assert items[0]["raw"].startswith("[4]")
    assert "25（010）：43-47" in items[0]["raw"]


def test_taskbook_reference_drops_college_stem_footer_residue():
    blocks = [
        _Block(1, "本科生毕业设计（论文）任务书"),
        _Block(2, "IV、主要参考资料："),
        _Block(3, "[4] 吴魁，王仙勇，孙洁，等. 基于深度学习的故障检测方法[J]. 计算机测量与控制，2017，25"),
        _Block(4, "（010）：43-47. 沈元"),
        _Block(5, "沈元学院 自动化 专业类 200300 班"),
        _Block(6, "本人声明"),
    ]

    task = extract_task_book_from_blocks(blocks, {"college": "沈元学院", "major": "自动化"})

    assert len(task["references"]) == 1
    assert task["references"][0]["raw"].endswith("25（010）：43-47.")
    assert "沈元" not in task["references"][0]["raw"]


def test_metadata_normalization_keeps_context_specific_major_values():
    normalized = normalize_metadata(
        {
            "college": "自动化科学与电气工程学院",
            "major": "自动化专业",
            "advisor": "唐荻音",
        }
    )

    assert normalized["college"]["normalized_value"] == "自动化科学与电气工程学院"
    assert normalized["college"]["school_stem"] == "自动化科学与电气工程"
    assert normalized["major"]["raw_value"] == "自动化专业"
    assert normalized["major"]["normalized_value"] == "自动化"
    assert normalized["major"]["display_for_taskbook"] == "自动化"


def test_metadata_normalization_extracts_major_class_and_class_name_separately():
    normalized = normalize_metadata(
        {
            "college": "自动化科学与电气工程学院",
            "major": "自动化 专业类 170325 班",
            "advisor": "唐荻音",
        }
    )

    assert normalized["major"]["raw_value"] == "自动化 专业类 170325 班"
    assert normalized["major"]["normalized_value"] == "自动化"
    assert normalized["major"]["display_for_cover"] == "自动化"
    assert normalized["major"]["display_for_taskbook"] == "自动化"
    assert normalized["major"]["major_class_display"] == "自动化 专业类"
    assert normalized["class_name"]["normalized_value"] == "170325"
    assert normalized["class_name"]["needs_review"] is False


def test_taskbook_bottom_fields_are_structured_and_reportable():
    blocks = [
        _Block(18, "本科毕业设计（论文）任务书"),
        _Block(19, "Ⅰ、毕业设计（论文）题目："),
        _Block(20, "基于实拍图像的光电系统性能评估关键技术研究"),
        _Block(21, "Ⅳ、主要参考资料："),
        _Block(22, "[1] Task reference."),
        _Block(35, "自动化科学与电气工程 学院 自动化 专业类 170325 班"),
        _Block(36, "学生 崔润昊"),
        _Block(40, "指导教师： 唐荻音"),
        _Block(43, "本人声明"),
    ]

    task = extract_task_book_from_blocks(blocks, {"college": "自动化科学与电气工程学院", "major": "自动化专业"})

    assert task["college"] == "自动化科学与电气工程学院"
    assert task["major_raw"] == "自动化"
    assert task["major_normalized"] == "自动化"
    assert task["major_class_display"] == "自动化 专业类"
    assert task["class_name"] == "170325"
    assert task["bottom_fields"]["college"] == "自动化科学与电气工程学院"
    assert task["bottom_fields"]["major_class"] == "自动化 专业类"


def test_latex_model_keeps_taskbook_references_separate_from_main_references(tmp_path: Path):
    source_model = {
        "metadata": {"title_cn": "题名", "college": "自动化科学与电气工程学院", "major": "自动化", "student_name": "崔润昊", "advisor": "唐荻音"},
        "front_matter": {},
        "task_book": {"references": [{"raw": "[1] Task reference."}], "raw_materials": "资料", "work_content": "工作"},
        "sections": [{"type": "chapter", "title": "1 绪论", "level": 1, "source": {"file": "source.docx", "paragraph_index": 1}}],
        "references": [{"text": "Main reference.", "source": {"file": "source.docx", "paragraph_index": 100}}],
        "figures": [],
        "equations": [],
    }

    model = _latex_model_from_thesis_model(source_model, "undergraduate")
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex"
    render_buaa_latex(model, template_path=template, degree_type="undergraduate", out_dir=out, compile_pdf=False)

    assign = (out / "workdir" / "data" / "bachelor" / "assign.tex").read_text(encoding="utf-8")
    references = (out / "workdir" / "data" / "reference.tex").read_text(encoding="utf-8")
    assert "{[1] Task reference.}" in assign
    assert "Main reference" not in assign
    assert "[1] Main reference." in references


def test_taskbook_references_are_kept_as_full_size_fixed_assignment_slots():
    long_reference = (
        "[1] Tang D, Gong M, Yu J, et al. System-level performance prediction for infrared systems "
        "based on energy redistribution in infrared images[J]. IEEE Transactions on Industrial Electronics, 2021."
    )

    assign = _assign({"task_book": {"references": [{"raw": long_reference}]}})
    assign_ref_lines = [line for line in assign.split(r"\assignRef", 1)[1].splitlines() if line.startswith("{")]

    assert len(assign_ref_lines) == 8
    assert long_reference in assign
    assert any("Tang D" in line for line in assign_ref_lines)
    assert "resizebox" not in assign
    assert "scriptsize" not in assign


def test_taskbook_references_keep_font_size_and_wrap_in_assignment_patch():
    references = [
        "[1] 张建奇. 红外系统 [M]. 西安电子科技大学出版社: 西安,2018:236",
        "[2] Sonka M, Hlavac V, Boyle R. 艾海舟, 苏延超译 [M]. 图像处理, 分析与机器视觉 (第三版), 2011: 86-102.",
        "[3] Tang D, Gong M, Yu J, et al. System-level performance prediction for infrared systems based on energy redistribution in infrared images[J]. IEEE Transactions on Industrial Electronics, 2021.",
        "[4] Boreman G D. Modulation transfer function in optical and electro-optical systems[M]. Bellingham, WA: SPIE press, 2001.",
        "[5] International Organization for Standardization. Photography: Electronic Still Picture Imaging-Resolution and Spatial Frequency Responses[M]. ISO, 2014",
    ]

    assign = _assign({"task_book": {"references": [{"raw": item} for item in references]}})
    patch = _assign_patch({"metadata": {"advisor": "唐荻音", "college": "自动化科学与电气工程学院", "major": "自动化"}})
    assign_ref_lines = [line for line in assign.split(r"\assignRef", 1)[1].splitlines() if line.startswith("{")]

    assert len(assign_ref_lines) == 8
    assert "resizebox" not in assign
    assert "scriptsize" not in assign
    assert all(item in assign for item in references)
    assert r"\buaaAssignRefBlock" in assign
    assert r"\buaaAssignRefBlock" in patch
    assert r"\buaaAssignRefParagraph" in assign
    assert r"\par\vspace{0.55em}%" not in assign
    assert r"\begin{spacing}{1.5}" in patch
    assert r"\hangindent" not in patch
    assert r"\zihao{-4}" in patch
    assert r"\raggedright" not in patch
    assert r"\sloppy" not in patch
    assert r"\ulinec[.42]{\buaaAssignCollegeFull}" in patch


def test_figure_block_uses_page_relative_dynamic_sizing_not_fixed_width():
    tex = _figure_block({"render_asset": "assets/figures/system.png", "caption": "系统组成"})

    assert r"width=0.85\textwidth" not in tex
    assert r"\adjustbox" in tex
    assert r"max width=\linewidth" in tex
    assert r"max height=0.55\textheight" in tex


def test_cover_title_spacing_is_patched_to_one_point_five():
    patch = _assign_patch({"metadata": {"title_cn": "基于实拍图像的光电系统性能评估关键技术研究", "advisor": "唐荻音"}})

    assert r"\centering{\heiti\zihao{2}\buaaCoverTitle}" in patch
    assert r"\begin{spacing}{1.5}" in patch
    assert r"基于实拍图像的光电系统性能评估\\[0.5\baselineskip]关键技术研究" in patch


def test_cover_title_manual_line_break_uses_visible_one_point_five_gap():
    patch = _assign_patch({"metadata": {"title_cn_lines": ["first title line", "second title line"]}})

    assert r"first title line\\[0.5\baselineskip]second title line" in patch


def test_cover_title_lines_avoid_short_orphan_tail():
    assert _cover_title_lines("基于实拍图像的光电系统性能评估关键技术研究") == [
        "基于实拍图像的光电系统性能评估",
        "关键技术研究",
    ]


def test_cover_title_lines_prefer_source_evidence_line_over_guessing():
    patch = _assign_patch(
        {
            "metadata": {
                "title_cn": "于实拍图像的光电系统性能评估关键技术研",
                "evidence": {"title_cn": {"evidence_text": "于实拍图像的光电系统性能评估"}},
            }
        }
    )

    assert r"于实拍图像的光电系统性能评估\\[0.5\baselineskip]关键技术研" in patch


def test_taskbook_first_page_spacing_is_not_double_spaced():
    patch = _assign_patch({"metadata": {"advisor": "唐荻音"}})

    assert r"{\linespread{2}" in patch
    assert r"{\linespread{1.5}" in patch


def test_abstract_keyword_lines_keep_upstream_template_behavior():
    patch = _assign_patch({"metadata": {"advisor": "唐荻音"}})

    assert r"\newcommand{\buaaCKeywordLine}" not in patch
    assert r"\newcommand{\buaaEKeywordLine}" not in patch
    assert r"\patchcmd{\endcabstract}" not in patch
    assert r"\patchcmd{\endeabstract}" not in patch


def test_final_references_use_hanging_indent_not_plain_noindent_paragraphs():
    tex = _references(
        {
            "references": [
                {"raw": "[1] Tang D, Gong M, Yu J, et al. System-level performance prediction for infrared systems based on energy redistribution in infrared images[J]. IEEE Transactions on Industrial Electronics, 2021."},
                {"raw": "[2] International Organization for Standardization. Photography: Electronic Still Picture Imaging-Resolution and Spatial Frequency Responses[M]. ISO, 2014."},
            ]
        }
    )

    assert r"\newcommand{\buaaMainReferenceEntry}" in tex
    assert r"\hangindent=2em" in tex
    assert r"\buaaMainReferenceEntry{[1] Tang D" in tex
    assert r"\noindent [1] Tang D" not in tex


def test_taskbook_text_blocks_can_add_lines_without_truncating_tail():
    raw_materials = (
        "本毕设的原始数据来源于中国知网，IEEE 等网络论文数据库。\n"
        "本毕设涉及基于实拍图像的光电系统性能评估关键技术的研究与分析，设计算法通过光电系统拍"
        "摄的图像实现性能参数调制传递函数 MTF 的自动计算，并通过实验设备验证利用实拍图像获得"
        "MTF 方法的正确性。开发相应的自动化软件平台，具备 MTF 计算、历史数据存储等功能，方"
        "便用户进行系统性能评估。"
    )

    lines = _assignment_text_lines(raw_materials, width=66)
    assign = _assign({"task_book": {"raw_materials": raw_materials}})

    assert len(lines) > 5
    assert all(_display_width(line) <= 66 for line in lines)
    assert "方便用户进行系统性能评估" in "".join(lines)
    assert r"\buaaAssignReqBlock" in assign
    assert "方便用户进行系统性能评估" in _without_cjk_breaks(assign)


def test_taskbook_text_blocks_preserve_source_paragraphs_for_natural_wrap():
    raw_materials = (
        "本毕设的原始数据来源于中国知网，IEEE 等网络论文数据库。\n"
        "本毕设涉及基于实拍图像的光电系统性能评估关键技术的研究与分析，设计算法通过光电系统拍摄的图像实现性能参数调制传递函数 MTF 的自动计算，并通过实验设备验证利用实拍图像获得 MTF 方法的正确性。开发相应的自动化软件平台，具备 MTF 计算、历史数据存储等功能，方便用户进行系统性能评估。"
    )

    assign = _assign({"task_book": {"raw_materials": raw_materials}})
    rendered_paragraphs = [
        line.removeprefix(r"  \buaaAssignTextParagraph{").removesuffix("}")
        for line in assign.splitlines()
        if line.startswith(r"  \buaaAssignTextParagraph{")
    ]
    rendered_paragraphs = [_without_cjk_breaks(item) for item in rendered_paragraphs]

    assert rendered_paragraphs[:2] == raw_materials.splitlines()
    assert "".join(rendered_paragraphs[:2]) == raw_materials.replace("\n", "")
    assert r"\buaaAssignTextLine" not in assign


def test_render_includes_supported_figures_and_reports_equations_without_leaking_ids(tmp_path: Path):
    png = tmp_path / "figure.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x81\x9b\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    model = {
        "degree_type": "undergraduate",
        "metadata": {
            "title_cn": "题名",
            "college": "自动化科学与电气工程学院",
            "major": "自动化",
            "student_name": "崔润昊",
            "advisor": "唐荻音",
            "date": "2021 年 5 月",
            "classification": "TP273",
            "unit_code": "10006",
            "student_id": "17375303",
            "author_en": "CUI Run-hao",
            "tutor_en": "TANG Di-yin",
        },
        "task_book": {"references": []},
        "abstract_cn": {"body": "摘要", "keywords": ["关键词"]},
        "abstract_en": {"body": "Abstract.", "keywords": ["keyword"]},
        "body": [
            {"type": "chapter", "number": "1", "title": "绪论"},
            {"type": "figure", "asset": str(png), "caption": "机载光电系统的组成", "number_hint": "1.1"},
        ],
        "references": [],
        "equations_need_review": [{"id": "eq-1", "source_text": "oleObject4.bin"}],
    }
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex"

    report = render_buaa_latex(model, template_path=template, degree_type="undergraduate", out_dir=out, compile_pdf=False)

    body_tex = (out / "workdir" / "data" / "body.tex").read_text(encoding="utf-8")
    assert r"\includegraphics" in body_tex
    assert "assets/figures/" in body_tex
    assert str(png) not in body_tex
    assert "oleObject4.bin" not in body_tex
    assert report["figures"]["bindings"] == 1
    assert report["equations"]["ole_objects"] == 1


def test_render_report_exposes_taskbook_reference_figure_and_equation_summary(tmp_path: Path):
    png = tmp_path / "formula-preview.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x81\x9b\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    model = {
        "degree_type": "undergraduate",
        "metadata": {
            "title_cn": "题名",
            "college": "自动化科学与电气工程学院",
            "major": "自动化",
            "student_name": "崔润昊",
            "advisor": "唐荻音",
            "date": "2021 年 5 月",
            "classification": "TP273",
            "unit_code": "10006",
            "student_id": "17375303",
        },
        "task_book": {
            "college": "自动化科学与电气工程学院",
            "major_class": "自动化 专业类",
            "class_name": "170325",
            "student_name": "崔润昊",
            "advisor": "唐荻音",
            "references": [{"raw": "[1] Task reference."}],
        },
        "abstract_cn": {"body": "摘要", "keywords": ["关键词"]},
        "abstract_en": {"body": "Abstract.", "keywords": ["keyword"]},
        "body": [
            {"type": "chapter", "number": "1", "title": "绪论"},
            {"type": "figure", "asset": "", "caption": "红外探测系统组成", "number_hint": "1.2", "missing_reason": "source_image_not_found"},
            {
                "type": "equation_preview",
                "id": "eq-1",
                "asset": str(png),
                "source_text": "oleObject4.bin",
                "needs_review": True,
                "conversion_status": "visual_preview_rendered_native_latex_missing",
            },
        ],
        "references": [{"raw": "[1] Main reference."}],
        "equations_need_review": [{"id": "eq-1", "source_text": "oleObject4.bin", "rendered_preview": True}],
    }
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex"

    report = render_buaa_latex(model, template_path=template, degree_type="undergraduate", out_dir=out, compile_pdf=False)

    assert report["task_book"]["bottom_fields"] == {
        "college": "自动化科学与电气工程学院",
        "major_class": "自动化 专业类",
        "class_name": "170325",
        "student_name": "崔润昊",
        "advisor": "唐荻音",
    }
    assert report["references"]["taskbook_count"] == 1
    assert report["references"]["main_count"] == 1
    assert report["references"]["bad_wrapping_detected"] is False
    assert report["figures"]["missing"][0]["number_hint"] == "1.2"
    assert report["figures"]["missing"][0]["caption"] == "红外探测系统组成"
    assert report["figures"]["missing"][0]["reason"] == "source_image_not_found"
    assert report["equations"]["total"] == 1
    assert report["equations"]["native_latex"] == 0
    assert report["equations"]["image_fallback"] == 1
    assert report["equations"]["placeholders"] == 0
    assert report["equations"]["needs_review"] == 1
    assert report["equations"]["native_latex_complete"] is False


def test_injected_figure_blocks_inherit_source_trace(tmp_path: Path):
    png = tmp_path / "figure.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x81\x9b\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    source_model = {
        "metadata": {"title_cn": "题名", "college": "学院", "major": "专业", "student_name": "学生", "advisor": "导师"},
        "front_matter": {},
        "task_book": {},
        "sections": [
            {
                "type": "chapter",
                "title": "1 Introduction",
                "level": 1,
                "text": "Before\nFigure 1.1 System diagram\nAfter",
                "source": {"file": "source.docx", "paragraph_index": 10, "confidence": 0.93},
            }
        ],
        "references": [],
        "figures": [{"path": str(png), "caption": "Figure 1.1 System diagram"}],
        "equations": [],
    }

    model = _latex_model_from_thesis_model(source_model, "undergraduate")
    figure = next(item for item in model["body"] if item.get("type") == "figure")

    assert figure["source_trace"]["source_file"] == "source.docx"
    assert figure["source_trace"]["paragraph_start"] == 10


def test_convertible_vector_figure_assets_are_bound_to_captions(tmp_path: Path):
    emf = tmp_path / "figure.emf"
    emf.write_bytes(b"fake-emf")
    source_model = {
        "metadata": {"title_cn": "Title", "college": "College", "major": "Major", "student_name": "Student", "advisor": "Advisor"},
        "front_matter": {},
        "task_book": {},
        "sections": [
            {
                "type": "chapter",
                "title": "1 Introduction",
                "level": 1,
                "text": "Before\nFigure 1.2 System diagram\nAfter",
                "source": {"file": "source.docx", "paragraph_index": 10, "confidence": 0.93},
            }
        ],
        "references": [],
        "figures": [{"path": str(emf), "caption": "Figure 1.2 System diagram"}],
        "equations": [],
    }

    model = _latex_model_from_thesis_model(source_model, "undergraduate")

    figure = next(item for item in model["body"] if item.get("type") == "figure")
    candidate = model["debug"]["figure_candidates"][0]
    assert figure["asset"] == str(emf)
    assert figure["number_hint"] == "1.2"
    assert not figure.get("missing_asset")
    assert candidate["supported"] is True
    assert candidate["conversion_required"] is True


def test_pdf_fragmented_figure_caption_binds_by_number_and_ignores_references(tmp_path: Path):
    png = tmp_path / "figure.png"
    png.write_bytes(b"fake-png")
    source_model = {
        "metadata": {"title_cn": "Title", "college": "College", "major": "Major", "student_name": "Student", "advisor": "Advisor"},
        "front_matter": {},
        "task_book": {},
        "sections": [
            {
                "type": "chapter",
                "title": "1 Introduction",
                "level": 1,
                "text": "Before\n\u56fe1.2\nIMU failure image\n\u56fe2.3\u4e2d\u7684(a) shows a waveform.\nAfter",
                "source": {"file": "source.pdf", "paragraph_index": 10, "confidence": 0.65},
            }
        ],
        "references": [],
        "figures": [{"path": str(png), "caption": "\u56fe 1.2 IMU failure image"}],
        "equations": [],
    }

    model = _latex_model_from_thesis_model(source_model, "undergraduate")

    figures = [item for item in model["body"] if item.get("type") == "figure"]
    assert len(figures) == 1
    assert figures[0]["asset"] == str(png)
    assert figures[0]["caption"] == "IMU failure image"
    assert figures[0]["number_hint"] == "1.2"
    assert not figures[0].get("missing_asset")
    assert model["debug"]["figure_needs_review"] == []
    assert all(caption["raw"] != "\u56fe2.3\u4e2d\u7684(a) shows a waveform." for caption in model["debug"]["figure_captions"])


def test_latex_gate_does_not_treat_graphic_width_as_zero_heading(tmp_path: Path):
    out = tmp_path / "latex"
    data_dir = out / "workdir" / "data"
    data_dir.mkdir(parents=True)
    (out / "template_inspection.json").write_text("{}", encoding="utf-8")
    (out / "thesis.tex").write_text(r"\begin{document}\maketitle\end{document}", encoding="utf-8")
    (data_dir / "body.tex").write_text(
        "\n".join(
            [
                r"\chapter{绪论}",
                r"\includegraphics[width=0.85\textwidth]{assets/figures/image5.png}",
            ]
        ),
        encoding="utf-8",
    )
    extraction_result = {"gate_board": {"E02": {"status": "pass"}, "E08": {"status": "pass"}}}

    result = _write_latex_gate_reports(
        out,
        {"body": [{"type": "chapter", "title": "绪论"}]},
        {"compile_status": {"status": "skipped"}},
        extraction_result,
    )

    assert result["gate_board"]["G22"]["status"] == "pass"
    assert not any(item["reason"] == "zero_numbered_heading_in_tex" for item in result["failure_queue"])
    assert result["gate_board"]["G28"]["name"] == "latex_layout_contract"
    assert all(
        {
            "id",
            "gate",
            "reason",
            "region",
            "evidence_text",
            "expected",
            "suggested_fix",
            "can_fix_now",
        }.issubset(item)
        for item in result["failure_queue"]
    )
