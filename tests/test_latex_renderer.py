from __future__ import annotations

import json
from pathlib import Path

from buaa_thesis_kit.latex_renderer import render_latex


def _write_model(tmp_path: Path) -> Path:
    model = {
        "metadata": {
            "unit_code": "10006",
            "student_id": "17375303",
            "classification": "TP273",
            "title_cn": "基于实拍图像的光电系统性能评估\n关键技术研究",
            "title_en": "Photo-based Performance Evaluation of Optoelectronic Systems",
            "college": "自动化科学与电气工程学院",
            "major": "自动化",
            "student_name": "崔润昊",
            "advisor": "唐荻音",
            "date": "2021 年 5 月",
        },
        "front_matter": {
            "chinese_abstract": "本文研究光电系统性能评估方法。",
            "keywords_cn": "光电系统；性能评估",
            "english_abstract": "This thesis studies performance evaluation methods.",
            "keywords_en": "optoelectronic system; performance evaluation",
            "acknowledgement": "感谢导师的指导。",
        },
        "sections": [
            {
                "id": "sec-1",
                "type": "chapter",
                "title": "1 绪论",
                "text": "本章介绍研究背景。",
                "level": 1,
            },
            {
                "id": "sec-1-1",
                "type": "section",
                "title": "1.1 研究意义",
                "text": "光电系统测试需要稳定流程。",
                "level": 2,
            },
        ],
        "figures": [
            {
                "id": "fig-missing",
                "type": "image",
                "path": "image/missing.png",
                "caption": "缺失的系统框图",
            }
        ],
        "equations": [
            {
                "id": "eq-latex",
                "kind": "latex",
                "latex": "E = mc^2",
                "number": "(1-1)",
                "requires_review": False,
            },
            {
                "id": "eq-omml",
                "kind": "omml",
                "text": "x+y",
                "number": "(1-2)",
                "requires_review": True,
            },
        ],
        "references": [
            {
                "id": "ref-1",
                "type": "reference",
                "text": "[1] Wang. Test & evaluation_2026.",
            }
        ],
    }
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    return model_path


def test_render_latex_generates_buaa_thesis_source_and_report(tmp_path: Path):
    out_dir = tmp_path / "latex_spike"
    result = render_latex(
        _write_model(tmp_path),
        out_dir,
        compile_pdf=False,
        backend="lightweight",
    )

    thesis_tex = out_dir / "thesis.tex"
    report_json = out_dir / "report.json"
    assert result["tex_path"] == str(thesis_tex)
    assert thesis_tex.exists()
    assert report_json.exists()

    tex = thesis_tex.read_text(encoding="utf-8")
    assert r"\documentclass[UTF8,a4paper,12pt,oneside]{ctexbook}" in tex
    assert "毕业设计(论文)" in tex
    assert "10006" in tex
    assert "17375303" in tex
    assert "TP273" in tex
    assert "基于实拍图像的光电系统性能评估" in tex
    assert "关键技术研究" in tex
    assert "本文研究光电系统性能评估方法。" in tex
    assert "This thesis studies performance evaluation methods." in tex
    assert r"\tableofcontents" in tex
    assert r"\chapter{绪论}" in tex
    assert r"\section{研究意义}" in tex
    assert r"\[E = mc^2\]" in tex
    assert "公式占位：eq-omml" in tex
    assert "图像占位：缺失的系统框图" in tex
    assert r"Test \& evaluation\_2026" in tex

    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["template_used"].endswith("templates/latex/buaa/main.tex.template")
    assert report["compile_status"]["status"] == "skipped"
    assert report["missing_assets"] == [
        {
            "id": "fig-missing",
            "path": "image/missing.png",
            "caption": "缺失的系统框图",
            "reason": "missing or unsupported figure asset",
        }
    ]
    assert report["unsupported_equations"] == [
        {
            "id": "eq-omml",
            "kind": "omml",
            "number": "(1-2)",
            "reason": "equation has no trusted latex representation",
        }
    ]
    assert report["unsupported_figures"] == []
    assert "rendered declaration" in report["warnings"]


def test_default_bachelor_renderer_uses_bhosc_project_layout(tmp_path: Path):
    out_dir = tmp_path / "latex_bachelor"
    result = render_latex(_write_model(tmp_path), out_dir, compile_pdf=False)

    assert result["degree"] == "bachelor"
    assert result["workflow_part"] == "undergraduate"
    assert result["template_backend"] == "bhosc"
    assert result["reference_sample_pdf"].endswith("/sample-bachelor.pdf")
    assert (out_dir / "buaathesis.cls").exists()
    assert (out_dir / "figure" / "buaaname.pdf").exists()
    assert (out_dir / "data" / "com_info.tex").exists()
    assert (out_dir / "data" / "bachelor" / "bachelor_info.tex").exists()
    assert (out_dir / "data" / "bachelor" / "assign.tex").exists()
    assert (out_dir / "data" / "abstract.tex").exists()
    assert (out_dir / "data" / "body.tex").exists()

    thesis = (out_dir / "thesis.tex").read_text(encoding="utf-8")
    assert r"\documentclass[bachelor,openany,oneside,color,AutoFakeBold=true]{buaathesis}" in thesis
    assert r"\include{data/bachelor/assign}" in thesis
    assert r"\maketitle" in thesis

    info = (out_dir / "data" / "com_info.tex").read_text(encoding="utf-8")
    assert r"\school" in info
    assert "{自动化科学与电气工程学院}{ }" in info
    assert "{基于实拍图像的光电系统性能评估}" in info
    assert "{关键技术研究}" in info
    assert r"\category{TP273}" in info


def test_master_renderer_uses_separate_bhosc_profile(tmp_path: Path):
    out_dir = tmp_path / "latex_master"
    result = render_latex(
        _write_model(tmp_path),
        out_dir,
        degree="master",
        compile_pdf=False,
    )

    assert result["degree"] == "master"
    assert result["workflow_part"] == "graduate"
    assert result["template_backend"] == "bhosc"
    assert result["reference_sample_pdf"].endswith("/sample-master.pdf")
    assert (out_dir / "data" / "master" / "master_info.tex").exists()
    assert not (out_dir / "data" / "bachelor" / "assign.tex").exists()

    thesis = (out_dir / "thesis.tex").read_text(encoding="utf-8")
    assert r"\documentclass[master,openright,twoside,color,AutoFakeBold=true]{buaathesis}" in thesis
    assert r"\include{data/master/master_info}" in thesis
    assert r"\include{data/bachelor/assign}" not in thesis


def test_master_renderer_uses_renderable_empty_latex_fields(tmp_path: Path):
    out_dir = tmp_path / "latex_master"
    render_latex(
        _write_model(tmp_path),
        out_dir,
        degree="master",
        compile_pdf=False,
    )

    info = (out_dir / "data" / "com_info.tex").read_text(encoding="utf-8")
    assert r"{\mbox{}}" in info
    assert r"\school" in info
    assert r"\major" in info
