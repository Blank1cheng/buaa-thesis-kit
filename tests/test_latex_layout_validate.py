from __future__ import annotations

from pathlib import Path

from buaa_thesis_kit.latex.layout_validate import validate_layout


FAILURE_KEYS = {
    "id",
    "gate",
    "reason",
    "region",
    "evidence_text",
    "expected",
    "suggested_fix",
    "can_fix_now",
}


def _write_contract_files(out: Path, *, color: bool = False, spine: bool = True) -> None:
    data = out / "workdir" / "data"
    bachelor = data / "bachelor"
    bachelor.mkdir(parents=True)
    options = "a4paper,openany,color" if color else "a4paper,openany"
    (out / "thesis.tex").write_text(
        f"\\documentclass[{options}]{{buaathesis}}\n"
        + ("\\include{data/bachelor/spine}\n" if spine else "")
        + "\\maketitle\n",
        encoding="utf-8",
    )
    (bachelor / "spine.tex").write_text("\\newcommand{\\buaaSpinePage}{spine}\n", encoding="utf-8")
    (bachelor / "assign.tex").write_text(
        "\\buaaAssignTextParagraph{技术要求\\allowbreak{}文本}\n"
        "\\buaaAssignRefBlock\n",
        encoding="utf-8",
    )
    (bachelor / "assign_patch.tex").write_text(
        "\\newcommand{\\buaaAssignTextParagraph}[1]{#1}\n"
        "\\newcommand{\\buaaAssignRefParagraph}[1]{#1}\n"
        "\\zihao{-4}\\begin{spacing}{1.5}\\buaaAssignRefBlock\\end{spacing}\n",
        encoding="utf-8",
    )
    (data / "reference.tex").write_text(
        "\\par\\noindent\\hangindent=2em\\hangafter=1 [1] 正式参考文献\n",
        encoding="utf-8",
    )


def _model() -> dict:
    return {
        "metadata": {
            "classification": "TP273",
            "title_cn": "基于实拍图像的光电系统性能评估关键技术研究",
            "student_name": "崔润昊",
        },
        "task_book": {
            "date_range": "2020 年 12 月 18 日 至 2021 年 6 月 7 日",
            "references": ["[1] 第一条", "[2] 第二条"],
        },
    }


def _good_pages() -> list[str]:
    return [
        "TP273 基于实拍图像的光电系统性能评估关键技术研究",
        "基于实拍图像的光电系统性能评估关键技术研究 崔润昊 北京航空航天大学",
        "技术要求 工作内容",
        "主要参考资料 [1] 第一条 [2] 第二条 2020 年 12 月 18 日 至 2021 年 6 月 7 日",
        "本人声明",
        "摘 要",
        "Abstract",
        "目 录",
        "第 1 章 绪论",
    ]


def test_layout_validator_returns_stable_rich_failures(tmp_path: Path) -> None:
    _write_contract_files(tmp_path, color=True, spine=False)

    result = validate_layout(
        tmp_path,
        _model(),
        {"template_used": str(tmp_path / "tmp" / "BUAAthesis")},
        pdf_pages=["cover", "task book"],
        text_bounds={3: [], 4: []},
        render_evidence=False,
    )

    failures = {item["reason"]: item for item in result["failures"]}
    assert failures["template_depends_on_tmp"]["id"] == "H-G28-001"
    assert failures["frontmatter_spine_missing"]["id"] == "H-G28-004"
    assert failures["toc_color_not_black"]["id"] == "H-G28-005"
    assert set(failures["toc_color_not_black"]) == FAILURE_KEYS
    assert result["gate"]["status"] == "failed"


def test_layout_validator_accepts_taskbook_and_frontmatter_contract(tmp_path: Path) -> None:
    _write_contract_files(tmp_path)

    result = validate_layout(
        tmp_path,
        _model(),
        {"template_used": str(tmp_path / "templates" / "latex" / "buaa" / "bhosc")},
        pdf_pages=_good_pages(),
        text_bounds={
            3: [{"x0": 85.0, "x1": 548.0, "page_width": 595.0, "text": "技术要求"}],
            4: [{"x0": 85.0, "x1": 548.0, "page_width": 595.0, "text": "主要参考资料"}],
        },
        render_evidence=False,
    )

    assert result["gate"]["status"] == "pass"
    assert result["failures"] == []


def test_layout_validator_detects_taskbook_text_overflow(tmp_path: Path) -> None:
    _write_contract_files(tmp_path)

    result = validate_layout(
        tmp_path,
        _model(),
        {"template_used": str(tmp_path / "templates" / "latex" / "buaa" / "bhosc")},
        pdf_pages=_good_pages(),
        text_bounds={
            3: [{"x0": 85.0, "x1": 601.0, "page_width": 595.0, "text": "越界文本"}],
            4: [],
        },
        render_evidence=False,
    )

    failure = next(item for item in result["failures"] if item["reason"] == "taskbook_text_overflow")
    assert failure["id"] == "H-G28-010"
    assert failure["region"] == "taskbook.page_1"


def test_layout_validator_allows_abstracts_to_span_multiple_pages(tmp_path: Path) -> None:
    _write_contract_files(tmp_path)
    pages = _good_pages()[:6] + [
        "中文摘要续页",
        "Abstract English abstract first page",
        "English abstract continuation",
        "目 录 1 绪论",
        "第 1 章 绪论",
    ]

    result = validate_layout(
        tmp_path,
        _model(),
        {"template_used": str(tmp_path / "templates" / "latex" / "buaa" / "bhosc")},
        pdf_pages=pages,
        text_bounds={3: [], 4: []},
        render_evidence=False,
    )

    assert result["gate"]["status"] == "pass"
    assert result["failures"] == []
