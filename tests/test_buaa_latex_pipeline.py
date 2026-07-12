from __future__ import annotations

import hashlib
import json
from pathlib import Path

from buaa_thesis_kit.latex.pipeline import _latex_model_from_thesis_model, _pdf_has_zero_numbered_heading
from buaa_thesis_kit.latex.compile import compile_latex
from buaa_thesis_kit.latex.render_buaa import render_buaa_latex
from buaa_thesis_kit.latex.template_manager import inspect_buaa_template, resolve_buaa_template


def _fake_buaa_template(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "figure").mkdir()
    (root / "sample-bachelor.tex").write_text(
        r"""
\documentclass[bachelor,openany,oneside,color,AutoFakeBold=true]{buaathesis}
\begin{document}
\include{data/com_info}
\include{data/bachelor/bachelor_info}
\include{data/bachelor/assign}
\maketitle
\include{data/abstract}
\tableofcontents
\mainmatter
\include{data/chapter1-intro}
\include{data/reference}
\end{document}
""",
        encoding="utf-8",
    )
    (root / "sample-master.tex").write_text(
        r"""
\documentclass[master,openright,twoside,color,AutoFakeBold=true]{buaathesis}
\begin{document}
\include{data/com_info}
\include{data/master/master_info}
\maketitle
\include{data/abstract}
\tableofcontents
\mainmatter
\include{data/reference}
\end{document}
""",
        encoding="utf-8",
    )
    (root / "buaathesis.cls").write_text(
        r"""
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{buaathesis}
\LoadClass{ctexbook}
\newcommand{\school}[2]{}
\newcommand{\major}[2]{}
\newcommand{\thesistitle}[4]{}
\newcommand{\thesisauthor}[2]{}
\newcommand{\teacher}[2]{}
\newcommand{\category}[1]{}
\newcommand{\studentID}[1]{}
\newcommand{\unicode}[1]{}
\newcommand{\thesisdate}[2]{}
\newcommand{\ckeyword}[1]{}
\newcommand{\ekeyword}[1]{}
\renewcommand{\maketitle}{\chapter*{BUAA Template Cover}}
""",
        encoding="utf-8",
    )
    return root


def test_default_buaa_template_is_vendored_and_not_tmp():
    template = resolve_buaa_template()

    assert template.name == "bhosc"
    assert template.as_posix().endswith("templates/latex/buaa/bhosc")
    assert "tmp" not in template.parts
    assert (template / "buaathesis.cls").exists()


def _minimal_model() -> dict:
    return {
        "degree_type": "undergraduate",
        "metadata": {
            "unit_code": "10006",
            "student_id": "17375303",
            "classification": "TP273",
            "title_cn": "基于实拍图像的光电系统性能评估",
            "title_en": "Research on Electro-Optical System Evaluation",
            "college": "自动化科学与电气工程学院",
            "major": "自动化",
            "student_name": "崔润昊",
            "advisor": "唐荻音",
            "date": "2021 年 5 月",
        },
        "abstract_cn": {"body": "本文研究性能评估方法。", "keywords": ["光电系统", "性能评估"]},
        "abstract_en": {"body": "This thesis studies evaluation.", "keywords": ["evaluation"]},
        "body": [{"type": "chapter", "number": "1", "title": "绪论"}],
        "references": [{"raw": "[1] Reference item."}],
    }


def test_inspect_buaa_template_discovers_entrypoint_and_metadata_api(tmp_path: Path):
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "template_inspection.json"

    inspection = inspect_buaa_template(template, degree_type="undergraduate", output_path=out)

    assert inspection["degree_type"] == "undergraduate"
    assert inspection["entry"]["path"].endswith("sample-bachelor.tex")
    assert inspection["entry"]["documentclass_options"][0] == "bachelor"
    assert "data/com_info" in inspection["entry"]["includes"]
    assert inspection["metadata_api"]["school"]["args"] == 2
    assert inspection["metadata_api"]["thesistitle"]["args"] == 4
    assert inspection["figure_asset_dir"].endswith("figure")
    assert inspection["build_command"]["engine"] == "xelatex"
    assert out.exists()


def test_render_minimal_project_fills_buaathesis_variables_not_cover_layout(tmp_path: Path):
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"

    report = render_buaa_latex(
        _minimal_model(),
        template_path=template,
        degree_type="undergraduate",
        out_dir=out,
        compile_pdf=False,
    )

    thesis_tex = out / "thesis.tex"
    com_info = out / "workdir" / "data" / "com_info.tex"
    bachelor_info = out / "workdir" / "data" / "bachelor" / "bachelor_info.tex"
    body_tex = out / "workdir" / "data" / "body.tex"

    assert report["degree_type"] == "undergraduate"
    assert report["compile_status"]["status"] == "skipped"
    assert report["missing_assets"] == []
    assert report["unsupported_equations"] == []
    assert report["unsupported_figures"] == []
    assert thesis_tex.exists()
    assert r"\maketitle" in thesis_tex.read_text(encoding="utf-8")
    assert r"\begin{titlepage}" not in thesis_tex.read_text(encoding="utf-8")
    assert r"\thesistitle" in com_info.read_text(encoding="utf-8")
    assert "{基于实拍图像的光电系统性能评估}" in com_info.read_text(encoding="utf-8")
    assert r"\school{自动化科学与电气工程}{ }" in com_info.read_text(encoding="utf-8")
    assert r"\studentID{17375303}" in bachelor_info.read_text(encoding="utf-8")
    assert r"\chapter{绪论}" in body_tex.read_text(encoding="utf-8")
    assert r"\chapter{1 绪论}" not in body_tex.read_text(encoding="utf-8")
    assert (out / "template_inspection.json").exists()
    assert (out / "report.json").exists()


def test_latex_model_filters_source_toc_before_first_chapter_and_reports_it():
    source_model = {
        "metadata": {"student_name": "崔润昊", "advisor": "唐荻音"},
        "front_matter": {},
        "sections": [
            {"type": "section", "title": "1.1 课题来源与背景1", "level": 2, "source": {"file": "source.docx", "paragraph_index": 1, "confidence": 0.9}},
            {"type": "section", "title": "1.2 选题意义2", "level": 2, "source": {"file": "source.docx", "paragraph_index": 2, "confidence": 0.9}},
            {"type": "chapter", "title": "1 绪论", "level": 1, "source": {"file": "source.docx", "paragraph_index": 20, "confidence": 0.9}},
            {"type": "section", "title": "1.1 课题来源与背景", "level": 2, "source": {"file": "source.docx", "paragraph_index": 21, "confidence": 0.9}},
        ],
        "equations": [],
        "references": [],
    }

    model = _latex_model_from_thesis_model(source_model, "undergraduate")

    assert [item["type"] for item in model["body"][:2]] == ["chapter", "section"]
    assert model["body"][0]["number"] == "1"
    assert model["body"][0]["title"] == "绪论"
    assert model["body"][1]["number"] == "1.1"
    assert model["body"][1]["title"] == "课题来源与背景"
    assert model["debug"]["source_toc"][0]["title"] == "1.1 课题来源与背景1"


def test_latex_model_inserts_chapter_anchors_when_pdf_only_has_sections():
    source_model = {
        "metadata": {"student_name": "Student", "advisor": "Advisor"},
        "front_matter": {},
        "sections": [
            {"type": "section", "title": "1.1 Topic source", "level": 2, "text": "Body 1", "source": {"file": "source.pdf", "paragraph_index": 1}},
            {"type": "section", "title": "2.1 Method", "level": 2, "text": "Body 2", "source": {"file": "source.pdf", "paragraph_index": 2}},
        ],
        "equations": [],
        "references": [],
    }

    model = _latex_model_from_thesis_model(source_model, "undergraduate")

    headings = [
        (item.get("type"), item.get("number"), item.get("title"), item.get("synthetic_heading"))
        for item in model["body"]
        if item.get("type") in {"chapter", "section"}
    ]
    assert headings[:4] == [
        ("chapter", "1", "绪论", True),
        ("section", "1.1", "Topic source", None),
        ("chapter", "2", "第2章", True),
        ("section", "2.1", "Method", None),
    ]


def test_pdf_zero_numbered_heading_smoke_ignores_decimal_values():
    assert _pdf_has_zero_numbered_heading("AUC 值为 0.95329，RMSE 为 0.019011。") is False
    assert _pdf_has_zero_numbered_heading("0.1 时，预计剩余寿命为 12486 个时间单位。") is False
    assert _pdf_has_zero_numbered_heading("0.46 cos, 0 j W j X (2-21) 其中，W 为窗函数。") is False
    assert _pdf_has_zero_numbered_heading("0.015 a\uffff，人工选取目标区域。") is False
    assert _pdf_has_zero_numbered_heading("0.001 rad/mrad f\uffff(4-1) 其中，f 为焦距。") is False
    assert _pdf_has_zero_numbered_heading("0.1 错误小节标题\n正文") is True


def test_latex_model_keeps_equation_ole_objects_out_of_body_and_reports_them():
    source_model = {
        "metadata": {"student_name": "崔润昊", "advisor": "唐荻音"},
        "front_matter": {},
        "sections": [{"type": "chapter", "title": "1 绪论", "level": 1, "source": {"file": "source.docx", "paragraph_index": 1}}],
        "equations": [
            {"id": "eq-1", "kind": "embedded-object", "text": "oleObject4.bin", "source": {"file": "source.docx", "paragraph_index": 8}},
            {"id": "eq-2", "kind": "embedded-object", "text": "oleObject5.bin", "source": {"file": "source.docx", "paragraph_index": 9}},
        ],
        "references": [],
    }

    model = _latex_model_from_thesis_model(source_model, "undergraduate")

    assert not any(item.get("type") == "equation_placeholder" for item in model["body"])
    assert [item["id"] for item in model["equations_need_review"]] == ["eq-1", "eq-2"]


def test_latex_model_renders_trusted_latex_equations_and_reports_untrusted_ones(tmp_path: Path):
    source_model = {
        "metadata": {"student_name": "崔润昊", "advisor": "唐荻音"},
        "front_matter": {},
        "sections": [{"type": "chapter", "title": "1 绪论", "level": 1, "source": {"file": "source.docx", "paragraph_index": 1}}],
        "equations": [
            {
                "id": "eq-latex",
                "kind": "latex",
                "latex": r"MTF(f)=\frac{C_i(f)}{C_o(f)}",
                "requires_review": False,
                "source": {"file": "source.docx", "paragraph_index": 8},
            },
            {
                "id": "eq-omml",
                "kind": "omml",
                "text": "x+y",
                "requires_review": True,
                "source": {"file": "source.docx", "paragraph_index": 9},
            },
        ],
        "references": [],
    }
    model = _latex_model_from_thesis_model(source_model, "undergraduate")
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"

    report = render_buaa_latex(model, template_path=template, degree_type="undergraduate", out_dir=out, compile_pdf=False)

    body_tex = (out / "workdir" / "data" / "body.tex").read_text(encoding="utf-8")
    assert r"\begin{equation}" in body_tex
    assert r"MTF(f)=\frac{C_i(f)}{C_o(f)}" in body_tex
    assert [item["id"] for item in model["equations_need_review"]] == ["eq-omml"]
    assert [item["id"] for item in report["unsupported_equations"]] == ["eq-omml"]
    assert report["equations"]["native_latex_rendered"] == 1
    assert report["equations"]["workflow"]["trusted_latex"] == "rendered_as_native_latex"
    assert (
        report["equations"]["workflow"]["docx_omml_or_ole"]
        == "converted_only_after_native_compile_and_verification"
    )


def test_latex_model_renders_ole_equation_preview_images_without_native_claim(tmp_path: Path):
    preview = tmp_path / "equation-preview.png"
    preview.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
        b"\x00\x05\xfe\x02\xfeA\xe2!\xbc\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    source_model = {
        "metadata": {"student_name": "崔润昊", "advisor": "唐荻音"},
        "front_matter": {},
        "sections": [
            {
                "type": "chapter",
                "title": "1 绪论",
                "level": 1,
                "text": "公式前。\n__BUAA_EQUATION_eq-1__\n公式后。",
                "source": {"file": "source.docx", "paragraph_index": 1},
            }
        ],
        "equations": [
            {
                "id": "eq-1",
                "kind": "embedded-object",
                "text": "oleObject4.bin",
                "preview_path": str(preview),
                "requires_review": True,
                "source": {"file": "source.docx", "paragraph_index": 8},
            }
        ],
        "references": [],
    }
    model = _latex_model_from_thesis_model(source_model, "undergraduate")
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"

    report = render_buaa_latex(model, template_path=template, degree_type="undergraduate", out_dir=out, compile_pdf=False)

    body_types = [item["type"] for item in model["body"]]
    body_tex = (out / "workdir" / "data" / "body.tex").read_text(encoding="utf-8")
    assert body_types == ["chapter", "paragraph", "equation_preview", "paragraph"]
    assert "oleObject4.bin" not in body_tex
    assert r"\includegraphics" in body_tex
    assert "assets/equations/" in body_tex
    assert r"max height=2.0\baselineskip" in body_tex
    assert r"\textheight" not in body_tex
    assert model["equations_need_review"][0]["rendered_preview"] is True
    assert report["equations"]["equation_previews_rendered"] == 1
    assert report["equations"]["native_latex_rendered"] == 0


def test_latex_model_renders_inline_ole_equation_preview_inside_paragraph(tmp_path: Path):
    preview = tmp_path / "inline-equation-preview.png"
    preview.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
        b"\x00\x05\xfe\x02\xfeA\xe2!\xbc\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    source_model = {
        "metadata": {"student_name": "崔润昊", "advisor": "唐荻音"},
        "front_matter": {},
        "sections": [
            {
                "type": "chapter",
                "title": "1 绪论",
                "level": 1,
                "text": "其中，__BUAA_EQUATION_eq-1__ 是正弦光栅的振幅。",
                "source": {"file": "source.docx", "paragraph_index": 1},
            }
        ],
        "equations": [
            {
                "id": "eq-1",
                "kind": "embedded-object",
                "text": "oleObject4.bin",
                "preview_path": str(preview),
                "requires_review": True,
                "source": {"file": "source.docx", "paragraph_index": 8},
            }
        ],
        "references": [],
    }
    model = _latex_model_from_thesis_model(source_model, "undergraduate")
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"

    report = render_buaa_latex(model, template_path=template, degree_type="undergraduate", out_dir=out, compile_pdf=False)

    body_types = [item["type"] for item in model["body"]]
    body_tex = (out / "workdir" / "data" / "body.tex").read_text(encoding="utf-8")
    assert body_types == ["chapter", "paragraph_mixed"]
    assert "oleObject4.bin" not in body_tex
    assert r"\includegraphics[height=1.25em,keepaspectratio]" in body_tex
    assert r"\begin{center}" not in body_tex
    assert "其中，" in body_tex
    assert "是正弦光栅的振幅。" in body_tex
    assert report["equations"]["equation_previews_rendered"] == 1


def test_latex_model_stages_mathtype_native_stream_for_review(tmp_path: Path):
    preview = tmp_path / "inline-equation-preview.png"
    preview.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
        b"\x00\x05\xfe\x02\xfeA\xe2!\xbc\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    native = tmp_path / "eq-1.mtef"
    native.write_bytes(b"MTEF")
    source_model = {
        "metadata": {"student_name": "崔润昊", "advisor": "唐荻音"},
        "front_matter": {},
        "sections": [
            {
                "type": "chapter",
                "title": "1 绪论",
                "level": 1,
                "text": "其中，__BUAA_EQUATION_eq-1__ 是正弦光栅的振幅。",
                "source": {"file": "source.docx", "paragraph_index": 1},
            }
        ],
        "equations": [
            {
                "id": "eq-1",
                "kind": "embedded-object",
                "text": "oleObject4.bin",
                "preview_path": str(preview),
                "native_path": str(native),
                "native_format": "mathtype_mtef",
                "native_stream_name": "Equation Native",
                "native_sha256": "deadbeef",
                "native_size": 4,
                "requires_review": True,
                "source": {"file": "source.docx", "paragraph_index": 8},
            }
        ],
        "references": [],
    }
    model = _latex_model_from_thesis_model(source_model, "undergraduate")
    out = tmp_path / "latex_pipeline"

    from buaa_thesis_kit.latex.pipeline import _stage_latex_assets

    _stage_latex_assets(model, out)

    model_text = str(model)
    review_item = model["equations_need_review"][0]
    assert review_item["native_format"] == "mathtype_mtef"
    assert review_item["native_stream_name"] == "Equation Native"
    assert review_item["native_sha256"] == "deadbeef"
    assert review_item["native_size"] == 4
    assert review_item["native_asset"] == "debug/equations_native/eq-1.mtef"
    assert (out / "debug" / "equations_native" / "eq-1.mtef").read_bytes() == b"MTEF"
    assert "native_path" not in model_text
    assert str(tmp_path) not in model_text


def test_equation_report_counts_mathtype_native_stream_without_native_latex(tmp_path: Path):
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"
    model = _minimal_model()
    model["body"] = [
        {"type": "chapter", "number": "1", "title": "绪论"},
        {
            "type": "equation_preview",
            "id": "eq-1",
            "kind": "embedded-object",
            "render_asset": "assets/equations/eq-1.png",
        },
    ]
    model["equations_need_review"] = [
        {
            "id": "eq-1",
            "kind": "embedded-object",
            "source_text": "oleObject4.bin",
            "native_format": "mathtype_mtef",
            "native_stream_name": "Equation Native",
            "native_sha256": "deadbeef",
            "native_size": 4,
            "conversion_status": "mtef_native_available_converter_missing",
        }
    ]

    report = render_buaa_latex(model, template_path=template, degree_type="undergraduate", out_dir=out, compile_pdf=False)

    assert report["equations"]["native_streams_found"] == 1
    assert report["equations"]["mathtype_mtef"] == 1
    assert report["equations"]["native_latex"] == 0
    assert report["equations"]["native_latex_complete"] is False
    assert report["equations"]["conversion_tool"] == "mathtype_mtef_probe"


def test_render_strips_heading_numbers_and_does_not_emit_ole_filenames(tmp_path: Path):
    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"
    model = _minimal_model()
    model["metadata"]["author_en"] = "CUI Run-hao"
    model["metadata"]["tutor_en"] = "TANG Di-yin"
    model["body"] = [
        {"type": "chapter", "number": "1", "title": "绪论"},
        {"type": "section", "number": "1.1", "title": "课题来源与背景"},
    ]
    model["equations_need_review"] = [{"id": "eq-1", "source_text": "oleObject4.bin"}]

    report = render_buaa_latex(
        model,
        template_path=template,
        degree_type="undergraduate",
        out_dir=out,
        compile_pdf=False,
    )

    body_tex = (out / "workdir" / "data" / "body.tex").read_text(encoding="utf-8")
    com_info = (out / "workdir" / "data" / "com_info.tex").read_text(encoding="utf-8")
    assert r"\chapter{绪论}" in body_tex
    assert r"\section{课题来源与背景}" in body_tex
    assert "oleObject4.bin" not in body_tex
    assert rf"\thesisauthor{{{model['metadata']['student_name']}}}{{CUI Run-hao}}" in com_info
    assert rf"\teacher{{{model['metadata']['advisor']}}}{{TANG Di-yin}}" in com_info
    assert report["equations_need_review"] == 1
    assert report["unsupported_equations"][0]["source_text"] == "oleObject4.bin"


def test_compile_reports_skipped_when_tex_engine_missing(tmp_path: Path, monkeypatch):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    (workdir / "thesis.tex").write_text("content", encoding="utf-8")
    monkeypatch.setattr("buaa_thesis_kit.latex.compile.shutil.which", lambda _name: None)

    status = compile_latex(workdir, "thesis.tex")

    assert status["status"] == "skipped_missing_xelatex"
    assert (workdir / "compile.log").exists()


def test_run_latex_pipeline_cli_extracts_docx_and_renders_without_word_layout(tmp_path: Path):
    import scripts.run_latex_pipeline as cli

    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"
    source = Path("tests/fixtures/truncated_input.docx")

    exit_code = cli.main(
        [
            str(source),
            "--buaa-template-path",
            str(template),
            "--degree-type",
            "undergraduate",
            "--out",
            str(out),
            "--sample-mode",
            "truncated",
            "--no-compile",
        ]
    )

    assert exit_code == 0
    assert (out / "model.json").exists()
    assert (out / "thesis.tex").exists()
    assert (out / "report.json").exists()
    assert (out / "debug" / "metadata_candidates.json").exists()
    resolved_source = source.resolve()
    source_sha256 = hashlib.sha256(resolved_source.read_bytes()).hexdigest()
    model = json.loads((out / "model.json").read_text(encoding="utf-8"))
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    expected_identity = {
        "candidate_path": str(resolved_source),
        "source_sha256": source_sha256,
        "source_size": resolved_source.stat().st_size,
        "source_type": "docx",
    }
    assert model["source"] == expected_identity
    assert report["source_identity"] == expected_identity
    gate_board = json.loads(
        (out / "harness" / "gate_board.json").read_text(encoding="utf-8")
    )
    assert gate_board["G23"]["status"] == "needs_review"
    assert gate_board["G24"]["status"] == "failed"
    assert report["status"] == "failed"
    thesis_tex = (out / "thesis.tex").read_text(encoding="utf-8")
    assert r"\maketitle" in thesis_tex
    assert r"\begin{titlepage}" not in thesis_tex


def test_run_latex_pipeline_writes_extraction_harness_and_resolves_truncated_metadata(tmp_path: Path):
    import json
    import scripts.run_latex_pipeline as cli

    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"

    exit_code = cli.main(
        [
            "tests/fixtures/truncated_input.docx",
            "--buaa-template-path",
            str(template),
            "--degree-type",
            "undergraduate",
            "--out",
            str(out),
            "--sample-mode",
            "truncated",
            "--no-compile",
        ]
    )

    model = json.loads((out / "model.json").read_text(encoding="utf-8"))
    metadata_report = json.loads((out / "harness" / "metadata_report.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert model["metadata"]["student_name"] == "崔润昊"
    assert model["metadata"]["advisor"] == "唐荫韬"
    assert model["metadata"]["college"] == "自动化科学与电气工程学院"
    assert model["metadata"]["major"] == "自动化"
    assert metadata_report["missing"] == []
    assert (out / "harness" / "extraction_gate_board.json").exists()
    assert (out / "harness" / "gate_board.json").exists()


def test_run_latex_pipeline_writes_metadata_candidate_and_resolution_debug_reports(tmp_path: Path):
    import json
    import scripts.run_latex_pipeline as cli

    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"

    exit_code = cli.main(
        [
            "tests/fixtures/truncated_input.docx",
            "--buaa-template-path",
            str(template),
            "--degree-type",
            "undergraduate",
            "--out",
            str(out),
            "--sample-mode",
            "truncated",
            "--no-compile",
        ]
    )

    candidates = json.loads((out / "debug" / "metadata_candidates.json").read_text(encoding="utf-8"))
    resolution = json.loads((out / "debug" / "metadata_resolution.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert isinstance(candidates["advisor"], list)
    assert candidates["advisor"][0]["source_type"] == "docx"
    assert candidates["advisor"][0]["evidence"]
    assert "raw-docx-xml" in candidates["advisor"][0]["method"]
    assert resolution["advisor"]["value"] == "唐荫韬"
    assert resolution["advisor"]["source_evidence_count"] >= 1
    assert resolution["advisor"]["status"] in {"pass", "needs_review"}


def test_run_latex_pipeline_blocks_render_when_extraction_failed(tmp_path: Path, monkeypatch):
    from buaa_thesis_kit.models import ContentBlock, Metadata, SourceEvidence, ThesisModel
    import buaa_thesis_kit.latex.pipeline as pipeline

    template = _fake_buaa_template(tmp_path / "BUAAthesis")
    out = tmp_path / "latex_pipeline"

    def fake_extract(_source: Path, _work_dir: Path) -> ThesisModel:
        return ThesisModel(
            metadata=Metadata(title_cn="只有题名"),
            front_matter={"chinese_abstract": "摘要内容", "keywords_cn": "关键词"},
            sections=[
                ContentBlock(
                    id="sec-1",
                    type="chapter",
                    title="1 绪论",
                    source=SourceEvidence("source.docx", "test", paragraph_index=1, confidence=0.9, requires_review=False),
                )
            ],
        )

    monkeypatch.setattr(pipeline, "extract_thesis_model", fake_extract)

    report = pipeline.run_latex_pipeline(
        Path("tests/fixtures/truncated_input.docx"),
        template_path=template,
        degree_type="undergraduate",
        out_dir=out,
        compile_pdf=False,
        sample_mode="truncated",
    )

    assert report["status"] == "failed"
    assert report["blocked_by_extraction"] is True
    assert (out / "model.json").exists()
    assert (out / "harness" / "extraction_failure_queue.json").exists()
    assert not (out / "thesis.tex").exists()


def test_native_equation_results_only_promote_verified_conversions() -> None:
    import buaa_thesis_kit.latex.pipeline as pipeline

    model = {
        "equations": [
            {"id": "eq-1", "kind": "embedded-object", "requires_review": True, "preview_path": "eq-1.png"},
            {"id": "eq-2", "kind": "embedded-object", "requires_review": True, "preview_path": "eq-2.png"},
        ]
    }
    native_report = {
        "equations": [
            {
                "id": "eq-1",
                "status": "converted",
                "latex": r"E=mc^2",
                "conversion": {"method": "mathtype_sdk"},
                "visual": {"status": "pass", "score": 0.91},
            },
            {
                "id": "eq-2",
                "status": "candidate_needs_review",
                "latex": r"x=y",
                "conversion": {"method": "mathtype_sdk", "return_code": -14},
                "visual": {"status": "pass", "score": 0.88},
            },
        ],
        "failure_queue": [{"id": "H-EQ-003-eq-2", "region": "equations.eq-2"}],
    }

    promoted = pipeline._apply_native_equation_results(model, native_report)

    eq1, eq2 = promoted["equations"]
    assert eq1["kind"] == "latex"
    assert eq1["latex"] == r"E=mc^2"
    assert eq1["requires_review"] is False
    assert eq1["native_conversion"]["status"] == "converted"
    assert eq2["kind"] == "embedded-object"
    assert "latex" not in eq2
    assert eq2["requires_review"] is True
    assert eq2["native_conversion"]["failure_ids"] == ["H-EQ-003-eq-2"]

    body_items, review_items = pipeline._equation_items_from_source(promoted["equations"], 0)
    native_item = next(item for item in body_items if item["id"] == "eq-1")
    preview_item = next(item for item in body_items if item["id"] == "eq-2")
    assert native_item["native_conversion"]["status"] == "converted"
    assert review_items[0]["conversion_status"] == "mathtype_translator_warning"
    assert review_items[0]["workflow_action"] == "review_native_latex_candidate"

    from buaa_thesis_kit.latex import equation_render

    equation_report = equation_render.equation_report(
        review_items,
        [],
        [native_item],
        [preview_item],
    )
    assert equation_report["conversion_tool"] == "native_equation_pipeline"
    assert equation_report["native_pipeline_converted"] == 1
    assert equation_report["translator_warnings"] == 1
