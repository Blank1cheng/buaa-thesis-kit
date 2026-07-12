from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_DIR = ROOT / "templates" / "latex" / "buaa"
LIGHTWEIGHT_TEMPLATE = DEFAULT_TEMPLATE_DIR / "main.tex.template"
BHOSC_TEMPLATE_DIR = DEFAULT_TEMPLATE_DIR / "bhosc"
SUPPORTED_IMAGE_SUFFIXES = {".bmp", ".eps", ".jpg", ".jpeg", ".pdf", ".png"}
REFERENCE_SAMPLE_URLS = {
    "bachelor": "https://github.com/BHOSC/BUAAthesis/releases/download/v0.1/sample-bachelor.pdf",
    "master": "https://github.com/BHOSC/BUAAthesis/releases/download/v0.1/sample-master.pdf",
}
WORKFLOW_PARTS = {"bachelor": "undergraduate", "master": "graduate"}
REQUIRED_METADATA_FIELDS = [
    "unit_code",
    "student_id",
    "classification",
    "title_cn",
    "title_en",
    "college",
    "major",
    "student_name",
    "advisor",
    "date",
]

_TEX_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def render_latex(
    model_path: str | Path,
    out_dir: str | Path,
    *,
    template_dir: str | Path | None = None,
    compile_pdf: bool = True,
    degree: str = "bachelor",
    backend: str = "bhosc",
) -> dict[str, Any]:
    degree = _normalize_degree(degree)
    backend = _normalize_backend(backend)
    model_path = Path(model_path)
    out_dir = Path(out_dir)
    template_dir = Path(template_dir) if template_dir is not None else DEFAULT_TEMPLATE_DIR

    model = _load_model(model_path)
    warnings = _initial_warnings(model)
    report = _base_report(
        model_path=model_path,
        template_dir=template_dir,
        degree=degree,
        backend=backend,
        warnings=warnings,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    if backend == "bhosc":
        thesis_tex = _render_bhosc_project(
            model=model,
            out_dir=out_dir,
            source_dir=_bhosc_source_dir(template_dir),
            degree=degree,
            report=report,
            warnings=warnings,
        )
    else:
        thesis_tex = _render_lightweight_project(
            model=model,
            out_dir=out_dir,
            template_dir=template_dir,
            report=report,
            warnings=warnings,
        )

    report["tex_path"] = str(thesis_tex)
    if compile_pdf:
        report["compile_status"] = _compile_xelatex(thesis_tex, out_dir)
        thesis_pdf = out_dir / "thesis.pdf"
        if thesis_pdf.exists():
            report["pdf_path"] = str(thesis_pdf)
            report["visual_compare"] = _render_visual_compare(
                thesis_pdf=thesis_pdf,
                word_pdf=model_path.parent / "thesis.pdf",
                reference_pdf=_local_reference_sample(degree),
                out_dir=out_dir,
                warnings=warnings,
            )
    else:
        report["compile_status"] = {
            "status": "skipped",
            "engine": "xelatex",
            "reason": "compile_pdf=False",
        }

    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def tex_escape(text: Any) -> str:
    cleaned = _clean_text("" if text is None else str(text))
    return "".join(_TEX_ESCAPE_MAP.get(char, char) for char in cleaned)


def _base_report(
    *,
    model_path: Path,
    template_dir: Path,
    degree: str,
    backend: str,
    warnings: list[str],
) -> dict[str, Any]:
    if backend == "bhosc":
        template_used = _bhosc_source_dir(template_dir) / "buaathesis.cls"
    else:
        template_used = template_dir / "main.tex.template"
    return {
        "degree": degree,
        "workflow_part": WORKFLOW_PARTS[degree],
        "template_backend": backend,
        "template_used": _posix(template_used.resolve(strict=False)),
        "reference_sample_pdf": REFERENCE_SAMPLE_URLS[degree],
        "source_model": _posix(model_path.resolve(strict=False)),
        "source_model_sha256": _sha256(model_path) if model_path.exists() else "",
        "tex_path": "",
        "pdf_path": "",
        "template_assets": [],
        "compile_status": {"status": "not_run", "engine": "xelatex"},
        "missing_assets": [],
        "unsupported_equations": [],
        "unsupported_figures": [],
        "warnings": warnings,
        "visual_compare": {
            "latex_preview_pages": [],
            "word_preview_pages": [],
            "reference_sample_pages": [],
            "word_pdf": "",
            "reference_sample_pdf": "",
        },
    }


def _render_bhosc_project(
    *,
    model: dict[str, Any],
    out_dir: Path,
    source_dir: Path,
    degree: str,
    report: dict[str, Any],
    warnings: list[str],
) -> Path:
    _copy_bhosc_runtime(source_dir, out_dir, report, warnings)
    data_dir = out_dir / "data"
    (data_dir / "bachelor").mkdir(parents=True, exist_ok=True)
    (data_dir / "master").mkdir(parents=True, exist_ok=True)

    (data_dir / "com_info.tex").write_text(_bhosc_com_info(model, degree), encoding="utf-8")
    (data_dir / "abstract.tex").write_text(_bhosc_abstract(model), encoding="utf-8")
    (data_dir / "body.tex").write_text(_render_body(model, out_dir, report), encoding="utf-8")
    (data_dir / "reference.tex").write_text(_bhosc_references(model), encoding="utf-8")

    if degree == "bachelor":
        (data_dir / "bachelor" / "bachelor_info.tex").write_text(
            _bhosc_bachelor_info(model),
            encoding="utf-8",
        )
        (data_dir / "bachelor" / "assign.tex").write_text(
            _bhosc_assign(model, warnings),
            encoding="utf-8",
        )
        (data_dir / "bachelor" / "acknowledgement.tex").write_text(
            _bhosc_bachelor_acknowledgement(model),
            encoding="utf-8",
        )
        thesis = _bhosc_bachelor_main()
    else:
        (data_dir / "master" / "master_info.tex").write_text(
            _bhosc_master_info(model, warnings),
            encoding="utf-8",
        )
        (data_dir / "master" / "back2-acknowledgement.tex").write_text(
            _bhosc_master_acknowledgement(model),
            encoding="utf-8",
        )
        (data_dir / "master" / "back3-aboutauthor.tex").write_text(
            "% !Mode:: \"TeX:UTF-8\"\n\\chapter{作者简介}\n",
            encoding="utf-8",
        )
        thesis = _bhosc_master_main()

    thesis_tex = out_dir / "thesis.tex"
    thesis_tex.write_text(thesis, encoding="utf-8")
    return thesis_tex


def _render_lightweight_project(
    *,
    model: dict[str, Any],
    out_dir: Path,
    template_dir: Path,
    report: dict[str, Any],
    warnings: list[str],
) -> Path:
    if "rendered declaration" not in warnings:
        warnings.append("rendered declaration")
    template_path = template_dir / "main.tex.template"
    template = template_path.read_text(encoding="utf-8")
    replacements = {
        "<<COVER>>": _render_lightweight_cover(model),
        "<<DECLARATION>>": _render_lightweight_declaration(model),
        "<<ABSTRACT_CN>>": _render_abstract_cn(model),
        "<<ABSTRACT_EN>>": _render_abstract_en(model),
        "<<BODY>>": _render_body(model, out_dir, report),
        "<<ACKNOWLEDGEMENT>>": _render_acknowledgement(model),
        "<<REFERENCES>>": _render_lightweight_references(model),
    }
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)

    report["template_assets"] = _copy_template_assets(template_dir, out_dir, warnings)
    thesis_tex = out_dir / "thesis.tex"
    thesis_tex.write_text(rendered, encoding="utf-8")
    return thesis_tex


def _bhosc_bachelor_main() -> str:
    return r"""% !Mode:: "TeX:UTF-8"
\documentclass[bachelor,openany,oneside,color,AutoFakeBold=true]{buaathesis}

\usepackage{gbt7714}
\usepackage{booktabs}
\citestyle{numerical}

\begin{document}
\include{data/com_info}
\include{data/bachelor/bachelor_info}
\include{data/bachelor/assign}
\pagestyle{mainmatter}
\maketitle
\include{data/abstract}
\tableofcontents
\mainmatter
\include{data/body}
\include{data/bachelor/acknowledgement}
\include{data/reference}
\end{document}
"""


def _bhosc_master_main() -> str:
    return r"""% !Mode:: "TeX:UTF-8"
\documentclass[master,openright,twoside,color,AutoFakeBold=true]{buaathesis}

\usepackage{gbt7714}
\usepackage{booktabs}
\citestyle{numerical}

\begin{document}
\include{data/com_info}
\include{data/master/master_info}
\maketitle
\pagestyle{frontmatter}
\include{data/abstract}
\tableofcontents
\listoffigures
\listoftables
\mainmatter
\pagestyle{mainmatter}
\include{data/body}
\include{data/reference}
\backmatter
\include{data/master/back2-acknowledgement}
\include{data/master/back3-aboutauthor}
\end{document}
"""


def _bhosc_com_info(model: dict[str, Any], degree: str) -> str:
    metadata = _metadata(model)
    title_line_1, title_line_2 = _title_pair(_value(metadata, "title_cn"))
    year, month, day = _date_parts(_value(metadata, "date"))
    empty = r"\mbox{}" if degree == "master" else " "
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            "",
            rf"\school{{{_tex_value(_value(metadata, 'college'), empty)}}}{{{empty}}}",
            rf"\major{{{_tex_value(_value(metadata, 'major'), empty)}}}{{{empty}}}",
            r"\thesistitle",
            rf"{{{_tex_value(title_line_1, empty)}}}",
            rf"{{{_tex_value(title_line_2, empty)}}}",
            rf"{{{_tex_value(_value(metadata, 'title_en'), empty)}}}",
            rf"{{{empty}}}",
            rf"\thesisauthor{{{_tex_value(_value(metadata, 'student_name'), empty)}}}{{{empty}}}",
            rf"\teacher{{{_tex_value(_value(metadata, 'advisor'), empty)}}}{{{empty}}}",
            rf"\category{{{tex_escape(_value(metadata, 'classification'))}}}",
            rf"\thesisbegin{{{year}}}{{{month}}}{{{day}}}",
            rf"\thesisend{{{year}}}{{{month}}}{{{day}}}",
            rf"\defense{{{year}}}{{{month}}}{{{day}}}",
            rf"\ckeyword{{{tex_escape(_front_value(model, 'keywords_cn', 'chinese_keywords', 'cn_keywords', 'keywords'))}}}",
            rf"\ekeyword{{{tex_escape(_front_value(model, 'keywords_en', 'english_keywords', 'en_keywords'))}}}",
            "",
        ]
    )


def _bhosc_bachelor_info(model: dict[str, Any]) -> str:
    metadata = _metadata(model)
    year, month, _day = _date_parts(_value(metadata, "date"))
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            "",
            r"\class{}",
            rf"\studentID{{{tex_escape(_value(metadata, 'student_id'))}}}",
            rf"\unicode{{{tex_escape(_value(metadata, 'unit_code') or '10006')}}}",
            rf"\thesisdate{{{year}}}{{{month}}}",
            "",
        ]
    )


def _bhosc_master_info(model: dict[str, Any], warnings: list[str]) -> str:
    metadata = _metadata(model)
    year, month, day = _date_parts(_value(metadata, "date"))
    student_id = _value(metadata, "student_id")
    unit_code = _value(metadata, "unit_code") or "10006"
    thesis_id = f"{unit_code}{student_id}" if student_id else ""
    if not _front_value(model, "direction"):
        warnings.append("missing master field: direction")
    if not _front_value(model, "teacher_degree"):
        warnings.append("missing master field: teacher_degree")
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            "",
            rf"\direction{{{tex_escape(_front_value(model, 'direction'))}}}",
            rf"\teacherdegree{{{tex_escape(_front_value(model, 'teacher_degree'))}}}{{ }}",
            r"\applydegree{}",
            rf"\thesisID{{{tex_escape(thesis_id)}}}",
            rf"\commit{{{year}}}{{{month}}}{{{day}}}",
            rf"\award{{{year}}}{{{month}}}{{{day}}}",
            "",
        ]
    )


def _bhosc_assign(model: dict[str, Any], warnings: list[str]) -> str:
    req = _front_lines(model, "assign_req", "task_requirements", count=5)
    work = _front_lines(model, "assign_work", "task_work", count=6)
    refs = _reference_lines(model, count=8)
    if not any(req + work + refs):
        warnings.append("missing bachelor task book fields; generated blank BHOSC task book")
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            "",
            _macro_lines("assignReq", req),
            _macro_lines("assignWork", work),
            _macro_lines("assignRef", refs),
            "",
        ]
    )


def _bhosc_abstract(model: dict[str, Any]) -> str:
    chinese = _front_value(model, "chinese_abstract", "abstract_cn", "cn_abstract")
    english = _front_value(model, "english_abstract", "abstract_en", "en_abstract")
    blocks = ['% !Mode:: "TeX:UTF-8"', ""]
    if chinese:
        blocks.extend([r"\begin{cabstract}", _render_paragraphs(chinese), r"\end{cabstract}", ""])
    if english:
        blocks.extend([r"\begin{eabstract}", _render_paragraphs(english), r"\end{eabstract}", ""])
    return "\n".join(blocks)


def _bhosc_bachelor_acknowledgement(model: dict[str, Any]) -> str:
    text = _acknowledgement_text(model)
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            r"\chapter*{致谢}",
            r"\addcontentsline{toc}{chapter}{致谢}",
            _render_paragraphs(text) if text else "",
            r"\cleardoublepage",
            "",
        ]
    )


def _bhosc_master_acknowledgement(model: dict[str, Any]) -> str:
    text = _acknowledgement_text(model)
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            r"\chapter{致谢}",
            _render_paragraphs(text) if text else "",
            "",
        ]
    )


def _bhosc_references(model: dict[str, Any]) -> str:
    references = model.get("references") or []
    if not references:
        return '% !Mode:: "TeX:UTF-8"\n\\cleardoublepage\n'
    lines = [
        '% !Mode:: "TeX:UTF-8"',
        r"\cleardoublepage",
        r"\phantomsection",
        r"\addcontentsline{toc}{chapter}{参考文献}",
        r"\chapter*{参考文献}",
    ]
    for reference in references:
        text = str(reference.get("text") or reference.get("title") or "")
        if text.strip():
            lines.append(rf"\noindent {tex_escape(text)}\par")
    lines.append(r"\cleardoublepage")
    return "\n".join(lines) + "\n"


def _copy_bhosc_runtime(
    source_dir: Path,
    out_dir: Path,
    report: dict[str, Any],
    warnings: list[str],
) -> None:
    required_files = [
        "buaathesis.cls",
        "gbt7714.sty",
        "gbt7714-numerical.bst",
        "gbt7714-author-year.bst",
    ]
    copied: list[str] = []
    for name in required_files:
        source = source_dir / name
        if not source.exists():
            warnings.append(f"missing BHOSC runtime file: {_posix(source)}")
            continue
        target = out_dir / name
        shutil.copy2(source, target)
        copied.append(str(target))

    source_figure_dir = source_dir / "figure"
    target_figure_dir = out_dir / "figure"
    target_figure_dir.mkdir(parents=True, exist_ok=True)
    if source_figure_dir.exists():
        for source in source_figure_dir.iterdir():
            if source.is_file():
                target = target_figure_dir / source.name
                shutil.copy2(source, target)
                copied.append(str(target))
    else:
        warnings.append(f"missing BHOSC figure directory: {_posix(source_figure_dir)}")
    report["template_assets"] = copied


def _load_model(model_path: Path) -> dict[str, Any]:
    return json.loads(model_path.read_text(encoding="utf-8"))


def _initial_warnings(model: dict[str, Any]) -> list[str]:
    warnings = list(model.get("extraction_warnings") or [])
    metadata = _metadata(model)
    for field in REQUIRED_METADATA_FIELDS:
        if not _value(metadata, field):
            warnings.append(f"missing metadata field: {field}")
    if not _front_value(model, "chinese_abstract", "abstract_cn", "cn_abstract"):
        warnings.append("missing chinese abstract")
    if not _front_value(model, "english_abstract", "abstract_en", "en_abstract"):
        warnings.append("missing english abstract")
    if not model.get("references"):
        warnings.append("missing references")
    warnings.append("LaTeX spike template is parallel to Word renderer; Word failures remain visible")
    return _dedupe(warnings)


def _render_lightweight_cover(model: dict[str, Any]) -> str:
    metadata = _metadata(model)
    title_lines = _title_lines(_value(metadata, "title_cn"))
    rendered_title = r"\\[0.4ex]".join(tex_escape(line) for line in title_lines) or r"\mbox{}"
    return rf"""
\begin{{titlepage}}
\thispagestyle{{empty}}
\vspace*{{-8mm}}
\noindent
\IfFileExists{{figure/buaamark.pdf}}{{\includegraphics[width=90pt]{{figure/buaamark.pdf}}}}{{\heiti 北京航空航天大学}}
\hfill
\raisebox{{-2mm}}[0pt][0pt]{{%
  \zihao{{5}}\heiti
  \begin{{tabular}}{{rl}}
    单位代码 & {{\zihao{{-4}}\rmfamily \BUAAShortUnderline{{{tex_escape(_value(metadata, "unit_code"))}}}}}\\[0.1ex]
    学\qquad 号 & {{\zihao{{-4}}\rmfamily \BUAAShortUnderline{{{tex_escape(_value(metadata, "student_id"))}}}}}\\[0.1ex]
    分~~类~~号 & {{\zihao{{-4}}\rmfamily \BUAAShortUnderline{{{tex_escape(_value(metadata, "classification"))}}}}}
  \end{{tabular}}
}}
\vspace{{34mm}}
\begin{{center}}
\IfFileExists{{figure/buaaname.pdf}}{{\includegraphics[width=360bp]{{figure/buaaname.pdf}}}}{{\zihao{{1}}\heiti 北京航空航天大学}}
\vspace{{18mm}}
{{\zihao{{0}}\heiti 毕业设计(论文)\par}}
\vspace{{20mm}}
{{\zihao{{2}}\heiti\setstretch{{1.5}} {rendered_title}\par}}
\vfill
{{\zihao{{-3}}\heiti
\begin{{tabular}}{{rl}}
学院名称 & \BUAALongUnderline{{{tex_escape(_value(metadata, "college"))}}}\\[0.9ex]
专业名称 & \BUAALongUnderline{{{tex_escape(_value(metadata, "major"))}}}\\[0.9ex]
学生姓名 & \BUAALongUnderline{{{tex_escape(_value(metadata, "student_name"))}}}\\[0.9ex]
指导教师 & \BUAALongUnderline{{{tex_escape(_value(metadata, "advisor"))}}}
\end{{tabular}}
}}
\vspace{{1.5\baselineskip}}
{{\zihao{{-3}}\heiti {tex_escape(_value(metadata, "date"))}\par}}
\end{{center}}
\end{{titlepage}}
"""


def _render_lightweight_declaration(model: dict[str, Any]) -> str:
    metadata = _metadata(model)
    return rf"""
\chapter*{{本人声明}}
\thispagestyle{{empty}}
本人郑重声明：所呈交的毕业设计（论文）是本人在指导教师指导下独立进行研究工作所取得的成果。除文中已经注明引用的内容外，本论文不包含任何其他个人或集体已经发表或撰写过的研究成果。

\vspace{{12mm}}
\noindent 论文题目：{tex_escape(_value(metadata, "title_cn"))}

\vspace{{10mm}}
\noindent 学生签名：\underline{{\makebox[35mm][c]{{}}}}\hfill
日期：{tex_escape(_value(metadata, "date"))}
\clearpage
"""


def _render_abstract_cn(model: dict[str, Any]) -> str:
    metadata = _metadata(model)
    abstract = _front_value(model, "chinese_abstract", "abstract_cn", "cn_abstract")
    keywords = _front_value(model, "keywords_cn", "chinese_keywords", "cn_keywords", "keywords")
    if not abstract and not keywords:
        return ""
    return rf"""
\chapter*{{摘\quad 要}}
\addcontentsline{{toc}}{{chapter}}{{摘要}}
\begin{{flushright}}
作者：{tex_escape(_value(metadata, "student_name"))}\\
指导教师：{tex_escape(_value(metadata, "advisor"))}
\end{{flushright}}
{_render_paragraphs(abstract)}

\vspace{{1em}}
\noindent\heiti 关键词：\songti {tex_escape(keywords)}
\clearpage
"""


def _render_abstract_en(model: dict[str, Any]) -> str:
    metadata = _metadata(model)
    abstract = _front_value(model, "english_abstract", "abstract_en", "en_abstract")
    keywords = _front_value(model, "keywords_en", "english_keywords", "en_keywords")
    if not abstract and not keywords:
        return ""
    title_en = _value(metadata, "title_en")
    title_block = rf"\begin{{center}}\zihao{{3}}\bfseries {tex_escape(title_en)}\end{{center}}" if title_en else ""
    return rf"""
\chapter*{{Abstract}}
\addcontentsline{{toc}}{{chapter}}{{Abstract}}
{title_block}
\begin{{flushright}}
Author: {tex_escape(_value(metadata, "student_name"))}\\
Tutor: {tex_escape(_value(metadata, "advisor"))}
\end{{flushright}}
{_render_paragraphs(abstract)}

\vspace{{1em}}
\noindent\textbf{{Key words: }}{tex_escape(keywords)}
\clearpage
"""


def _render_body(model: dict[str, Any], out_dir: Path, report: dict[str, Any]) -> str:
    blocks: list[str] = []
    for section in model.get("sections") or []:
        blocks.append(_render_section(section))
    blocks.extend(_render_table(table) for table in model.get("tables") or [])
    blocks.extend(_render_figure(figure, out_dir, report) for figure in model.get("figures") or [])
    blocks.extend(_render_equation(equation, report) for equation in model.get("equations") or [])
    return "\n\n".join(block for block in blocks if block).strip() + "\n"


def _render_section(section: dict[str, Any]) -> str:
    title = _strip_heading_number(str(section.get("title") or ""))
    command = _section_command(section)
    parts = [rf"\{command}{{{tex_escape(title)}}}"] if title else []
    text = str(section.get("text") or "")
    if text.strip():
        parts.append(_render_paragraphs(text))
    return "\n\n".join(parts)


def _render_table(table: dict[str, Any]) -> str:
    rows = _parse_table_rows(str(table.get("text") or ""))
    title = str(table.get("title") or "")
    if not rows:
        return "\n\n".join([rf"\paragraph{{{tex_escape(title)}}}", _render_paragraphs(table.get("text") or "")])
    column_count = max(len(row) for row in rows)
    body = []
    for row in rows:
        padded = row + [""] * (column_count - len(row))
        body.append(" & ".join(tex_escape(cell) for cell in padded) + r" \\")
    return "\n".join(
        [
            r"\begin{table}[htbp]",
            r"\centering",
            rf"\caption{{{tex_escape(title)}}}" if title else "",
            rf"\begin{{tabular}}{{{'l' * column_count}}}",
            r"\toprule",
            *body,
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )


def _render_figure(figure: dict[str, Any], out_dir: Path, report: dict[str, Any]) -> str:
    figure_id = str(figure.get("id") or "figure")
    caption = str(figure.get("caption") or figure_id)
    raw_path = str(figure.get("path") or "")
    resolved = _resolve_asset_path(raw_path, out_dir)
    if resolved is None:
        report["missing_assets"].append(
            {
                "id": figure_id,
                "path": raw_path,
                "caption": caption,
                "reason": "missing or unsupported figure asset",
            }
        )
        return _figure_placeholder(figure_id, caption, "资产缺失或格式不支持")
    if resolved.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        report["unsupported_figures"].append(
            {
                "id": figure_id,
                "path": raw_path,
                "caption": caption,
                "reason": "unsupported figure suffix",
            }
        )
        return _figure_placeholder(figure_id, caption, "图像格式暂不支持")
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / f"{_safe_name(figure_id)}{resolved.suffix.lower()}"
    if resolved.resolve(strict=False) != target.resolve(strict=False):
        shutil.copy2(resolved, target)
    include_path = _posix(target.relative_to(out_dir))
    return "\n".join(
        [
            r"\begin{figure}[htbp]",
            r"\centering",
            rf"\includegraphics[width=0.82\textwidth]{{{include_path}}}",
            rf"\caption{{{tex_escape(caption)}}}",
            r"\end{figure}",
        ]
    )


def _figure_placeholder(figure_id: str, caption: str, reason: str) -> str:
    return "\n".join(
        [
            r"\begin{figure}[htbp]",
            r"\centering",
            rf"\BUAAPlaceholderBox{{图像占位：{tex_escape(caption)}}}{{{tex_escape(reason)}；ID：{tex_escape(figure_id)}}}",
            rf"\caption{{{tex_escape(caption)}}}",
            r"\end{figure}",
        ]
    )


def _render_equation(equation: dict[str, Any], report: dict[str, Any]) -> str:
    equation_id = str(equation.get("id") or "equation")
    kind = str(equation.get("kind") or "")
    latex = str(equation.get("latex") or "").strip()
    number = str(equation.get("number") or "")
    requires_review = bool(equation.get("requires_review", True))
    if latex and not requires_review:
        rendered = latex if _is_display_math(latex) else rf"\[{latex}\]"
        if number:
            return f"% Equation number: {tex_escape(number)}\n{rendered}"
        return rendered
    report["unsupported_equations"].append(
        {
            "id": equation_id,
            "kind": kind,
            "number": number,
            "reason": "equation has no trusted latex representation",
        }
    )
    detail = str(equation.get("text") or kind or "needs manual TeX transcription")
    return rf"\BUAAPlaceholderBox{{公式占位：{tex_escape(equation_id)}}}{{{tex_escape(detail)}}}"


def _render_acknowledgement(model: dict[str, Any]) -> str:
    text = _acknowledgement_text(model)
    if not text:
        return ""
    return "\n\n".join(
        [
            r"\chapter*{致谢}",
            r"\addcontentsline{toc}{chapter}{致谢}",
            _render_paragraphs(text),
        ]
    )


def _render_lightweight_references(model: dict[str, Any]) -> str:
    references = model.get("references") or []
    if not references:
        return ""
    lines = [r"\chapter*{参考文献}", r"\addcontentsline{toc}{chapter}{参考文献}"]
    for reference in references:
        text = str(reference.get("text") or reference.get("title") or "")
        if text.strip():
            lines.append(rf"\noindent {tex_escape(text)}\par")
    return "\n".join(lines)


def _render_paragraphs(text: Any) -> str:
    paragraphs = [line.strip() for line in _clean_text(str(text or "")).splitlines() if line.strip()]
    return "\n\n".join(tex_escape(paragraph) for paragraph in paragraphs)


def _tex_value(value: str, empty: str) -> str:
    return tex_escape(value) if str(value or "").strip() else empty


def _front_value(model: dict[str, Any], *keys: str) -> str:
    front_matter = model.get("front_matter") or {}
    for key in keys:
        value = front_matter.get(key)
        if isinstance(value, list):
            return "\n".join(str(item) for item in value if item)
        if value:
            return str(value)
    return ""


def _front_lines(model: dict[str, Any], *keys: str, count: int) -> list[str]:
    raw = _front_value(model, *keys)
    lines = [line.strip() for line in str(raw).splitlines() if line.strip()]
    return (lines + [""] * count)[:count]


def _reference_lines(model: dict[str, Any], count: int) -> list[str]:
    references = []
    for reference in model.get("references") or []:
        text = str(reference.get("text") or reference.get("title") or "").strip()
        if text:
            references.append(text)
    return (references + [""] * count)[:count]


def _macro_lines(name: str, values: list[str]) -> str:
    lines = [rf"\{name}"]
    lines.extend(rf"{{{tex_escape(value)}}}" for value in values)
    return "\n".join(lines)


def _metadata(model: dict[str, Any]) -> dict[str, Any]:
    return model.get("metadata") or {}


def _value(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key, "")
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item)
    return _clean_text(str(value or ""))


def _acknowledgement_text(model: dict[str, Any]) -> str:
    text = _front_value(model, "acknowledgement", "acknowledgements")
    if text:
        return text
    for section in model.get("sections") or []:
        if str(section.get("type") or "").lower() in {"acknowledgement", "acknowledgements"}:
            return str(section.get("text") or "")
    return ""


def _title_pair(title: str) -> tuple[str, str]:
    lines = _title_lines(title)
    if not lines:
        return "", ""
    if len(lines) == 1:
        return lines[0], ""
    return lines[0], " ".join(lines[1:])


def _title_lines(title: str) -> list[str]:
    explicit = [line.strip() for line in str(title or "").splitlines() if line.strip()]
    if len(explicit) > 1:
        return explicit
    if not explicit:
        return []
    text = explicit[0]
    if len(text) <= 18:
        return [text]
    midpoint = len(text) // 2
    candidates = [idx for idx, char in enumerate(text) if char in "，、；： -"]
    if candidates:
        split_at = min(candidates, key=lambda idx: abs(idx - midpoint)) + 1
    else:
        split_at = midpoint
    return [text[:split_at].strip(), text[split_at:].strip()]


def _date_parts(date: str) -> tuple[str, str, str]:
    numbers = re.findall(r"\d+", date or "")
    year = numbers[0] if len(numbers) >= 1 else ""
    month = numbers[1] if len(numbers) >= 2 else ""
    day = numbers[2] if len(numbers) >= 3 else ""
    return year, month, day


def _section_command(section: dict[str, Any]) -> str:
    block_type = str(section.get("type") or "").lower()
    level = int(section.get("level") or 0)
    if block_type in {"chapter", "section", "subsection"}:
        return block_type
    if level <= 1:
        return "chapter"
    if level == 2:
        return "section"
    return "subsection"


def _strip_heading_number(title: str) -> str:
    stripped = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s*", "", title).strip()
    return stripped or title.strip()


def _parse_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        if line.strip():
            rows.append([cell.strip() for cell in line.split("\t")])
    return rows


def _resolve_asset_path(raw_path: str, out_dir: Path) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.extend(
            [
                out_dir / path,
                ROOT / path,
                Path.cwd() / path,
                ROOT / "output" / "pipeline_gate" / path,
                ROOT / "output" / "pipeline_gate" / "image" / path.name,
            ]
        )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _is_display_math(latex: str) -> bool:
    return latex.startswith(r"\[") or latex.startswith("$$") or latex.startswith(r"\begin{")


def _compile_xelatex(thesis_tex: Path, out_dir: Path) -> dict[str, Any]:
    xelatex = shutil.which("xelatex")
    if not xelatex:
        return {
            "status": "skipped_no_xelatex",
            "engine": "xelatex",
            "reason": "xelatex not found on PATH",
        }

    runs: list[dict[str, Any]] = []
    status = "success"
    for index in (1, 2):
        completed = subprocess.run(
            [xelatex, "-interaction=nonstopmode", "-halt-on-error", thesis_tex.name],
            cwd=out_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        log_path = out_dir / f"xelatex_pass{index}.log.txt"
        combined_log = (completed.stdout or "") + "\n" + (completed.stderr or "")
        log_path.write_text(combined_log, encoding="utf-8", errors="replace")
        runs.append({"pass": index, "returncode": completed.returncode, "log_path": str(log_path)})
        if completed.returncode != 0:
            status = "failed"
            break

    pdf_path = out_dir / "thesis.pdf"
    return {
        "status": status if pdf_path.exists() or status == "failed" else "failed",
        "engine": "xelatex",
        "command": "xelatex -interaction=nonstopmode -halt-on-error thesis.tex",
        "runs": runs,
        "pdf_exists": pdf_path.exists(),
    }


def _copy_template_assets(template_dir: Path, out_dir: Path, warnings: list[str]) -> list[str]:
    source_figure_dir = template_dir / "figure"
    if not source_figure_dir.exists():
        warnings.append(f"LaTeX template figure directory not found: {_posix(source_figure_dir)}")
        return []
    target_figure_dir = out_dir / "figure"
    target_figure_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for source in source_figure_dir.iterdir():
        if source.is_file():
            target = target_figure_dir / source.name
            shutil.copy2(source, target)
            copied.append(str(target))
    return copied


def _render_visual_compare(
    *,
    thesis_pdf: Path,
    word_pdf: Path,
    reference_pdf: Path | None,
    out_dir: Path,
    warnings: list[str],
) -> dict[str, Any]:
    compare_dir = out_dir / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)
    latex_pages = _render_pdf_pages(thesis_pdf, compare_dir, "latex", warnings)
    word_pages: list[str] = []
    if word_pdf.exists():
        word_pages = _render_pdf_pages(word_pdf, compare_dir, "word", warnings)
    else:
        warnings.append(f"word pdf not found for visual comparison: {_posix(word_pdf)}")
    reference_pages: list[str] = []
    if reference_pdf and reference_pdf.exists():
        reference_pages = _render_pdf_pages(reference_pdf, compare_dir, "reference", warnings)
    return {
        "latex_preview_pages": latex_pages,
        "word_preview_pages": word_pages,
        "reference_sample_pages": reference_pages,
        "word_pdf": _posix(word_pdf.resolve(strict=False)) if word_pdf.exists() else "",
        "reference_sample_pdf": _posix(reference_pdf.resolve(strict=False)) if reference_pdf and reference_pdf.exists() else "",
    }


def _render_pdf_pages(pdf_path: Path, out_dir: Path, prefix: str, warnings: list[str]) -> list[str]:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover
        warnings.append(f"PyMuPDF unavailable for {prefix} preview: {exc}")
        return []
    rendered: list[str] = []
    try:
        document = fitz.open(pdf_path)
        for page_index in range(min(6, document.page_count)):
            page = document.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            target = out_dir / f"{prefix}_page_{page_index + 1:03d}.png"
            pix.save(target)
            rendered.append(str(target))
        document.close()
    except Exception as exc:  # pragma: no cover
        warnings.append(f"failed to render {prefix} preview: {exc}")
    return rendered


def _bhosc_source_dir(template_dir: Path) -> Path:
    candidate = template_dir / "bhosc"
    return candidate if candidate.exists() else template_dir


def _local_reference_sample(degree: str) -> Path | None:
    candidate = ROOT / "tmp" / "latex_refs" / "samples" / f"sample-{degree}.pdf"
    return candidate if candidate.exists() else None


def _normalize_degree(value: str) -> str:
    normalized = str(value or "bachelor").lower()
    aliases = {"undergraduate": "bachelor", "本科": "bachelor", "graduate": "master", "硕士": "master"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"bachelor", "master"}:
        raise ValueError("degree must be bachelor or master")
    return normalized


def _normalize_backend(value: str) -> str:
    normalized = str(value or "bhosc").lower()
    if normalized not in {"bhosc", "lightweight"}:
        raise ValueError("backend must be bhosc or lightweight")
    return normalized


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_text(text: str) -> str:
    return "".join(char for char in text if char == "\n" or char == "\t" or ord(char) >= 32)


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "asset"


def _posix(path: str | Path) -> str:
    return str(path).replace(os.sep, "/")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped
