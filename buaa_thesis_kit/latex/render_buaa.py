from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import equation_render, reference_render
from .assets import CONVERTIBLE_PREVIEW_EXTENSIONS, SUPPORTED_LATEX_IMAGE_EXTENSIONS, stage_latex_image_asset
from .compile import compile_latex
from .escape import tex_escape, tex_escape_with_cjk_breaks, tex_value
from .template_manager import inspect_buaa_template, normalize_degree_type, resolve_buaa_template


ASSIGNMENT_TEXT_WIDTH = 58
FIGURE_MAX_WIDTH = r"\linewidth"
FIGURE_MAX_HEIGHT = r"0.55\textheight"


def render_buaa_latex(
    model: dict[str, Any],
    *,
    template_path: str | Path,
    degree_type: str,
    out_dir: str | Path,
    compile_pdf: bool = True,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    workdir = out_dir / "workdir"
    out_dir.mkdir(parents=True, exist_ok=True)
    if workdir.exists():
        shutil.rmtree(workdir)
    for artifact in ("thesis.tex", "thesis.pdf", "compile.log", "report.json", "template_inspection.json"):
        path = out_dir / artifact
        if path.exists():
            path.unlink()
    workdir.mkdir(parents=True, exist_ok=True)

    degree = normalize_degree_type(degree_type)
    template_root = resolve_buaa_template(template_path)
    inspection = inspect_buaa_template(
        template_root,
        degree_type=degree,
        output_path=out_dir / "template_inspection.json",
    )
    _copy_template_runtime(template_root, workdir)
    _prepare_figure_assets(model, workdir)
    _write_buaa_project_files(model, degree, workdir)

    thesis_tex = workdir / "thesis.tex"
    public_tex = out_dir / "thesis.tex"
    shutil.copy2(thesis_tex, public_tex)
    model_path = out_dir / "model.json"
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")

    compile_status = {"status": "skipped", "reason": "compile_pdf=False"}
    if compile_pdf:
        compile_status = compile_latex(workdir, "thesis.tex")
        (out_dir / "compile.log").write_text(
            (workdir / "compile.log").read_text(encoding="utf-8", errors="replace"),
            encoding="utf-8",
            errors="replace",
        )
        pdf = workdir / "thesis.pdf"
        if pdf.exists():
            shutil.copy2(pdf, out_dir / "thesis.pdf")

    report = _report(model, degree, template_root, inspection, public_tex, out_dir, compile_status)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def empty_demo_model(degree_type: str = "undergraduate") -> dict[str, Any]:
    return {
        "degree_type": normalize_degree_type(degree_type),
        "metadata": {
            "unit_code": "10006",
            "student_id": "00000000",
            "classification": "TP312",
            "title_cn": "BUAAthesis 最小演示论文",
            "title_en": "Minimal BUAAthesis Demo",
            "college": "示例学院",
            "major": "示例专业",
            "student_name": "示例学生",
            "advisor": "示例导师",
            "date": "2026 年 7 月",
        },
        "task_book": {
            "title": "BUAAthesis 最小演示论文",
            "raw_materials": "",
            "work_content": "",
            "references": [],
        },
        "abstract_cn": {"body": "这是用于验证 BUAAthesis 模板变量填充的最小演示。", "keywords": ["模板", "演示"]},
        "abstract_en": {"body": "This is a minimal demo for BUAAthesis template filling.", "keywords": ["template", "demo"]},
        "body": [{"type": "chapter", "number": "1", "title": "绪论"}, {"type": "paragraph", "text": "正文最小占位内容。"}],
        "acknowledgement": "",
        "references": [],
    }


def _copy_template_runtime(template_root: Path, workdir: Path) -> None:
    for filename in ("buaathesis.cls", "gbt7714.sty", "gbt7714-numerical.bst", "gbt7714-author-year.bst"):
        source = template_root / filename
        if source.exists():
            shutil.copy2(source, workdir / filename)
    if (template_root / "figure").exists():
        shutil.copytree(template_root / "figure", workdir / "figure", dirs_exist_ok=True)


def _prepare_figure_assets(model: dict[str, Any], workdir: Path) -> None:
    figure_dir = workdir / "assets" / "figures"
    equation_dir = workdir / "assets" / "equations"
    used_names: set[str] = set()
    used_equation_names: set[str] = set()
    for item in _iter_asset_body_items(model.get("body") or []):
        source = Path(str(item.get("asset") or item.get("asset_path") or ""))
        if source and not source.is_absolute():
            source = workdir.parent / source
        if not source.exists() or source.suffix.lower() not in SUPPORTED_LATEX_IMAGE_EXTENSIONS | CONVERTIBLE_PREVIEW_EXTENSIONS:
            item["render_asset"] = ""
            item["needs_review"] = True
            continue
        target_dir = equation_dir if item.get("type") == "equation_preview" else figure_dir
        used_for_type = used_equation_names if item.get("type") == "equation_preview" else used_names
        target = stage_latex_image_asset(source, target_dir, used_for_type)
        if target is None:
            item["render_asset"] = ""
            item["needs_review"] = True
            continue
        asset_group = "equations" if item.get("type") == "equation_preview" else "figures"
        item["render_asset"] = f"assets/{asset_group}/{target.name}".replace("\\", "/")


def _iter_asset_body_items(body: list[Any]):
    for item in body:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"figure", "equation_preview"}:
            yield item
        for segment in item.get("segments") or []:
            if isinstance(segment, dict) and segment.get("type") == "equation_preview":
                yield segment


def _unique_asset_name(name: str, used_names: set[str]) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name).strip("._") or "figure.png"
    candidate = safe
    stem = Path(safe).stem
    suffix = Path(safe).suffix
    counter = 2
    while candidate in used_names:
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(candidate)
    return candidate


def _write_buaa_project_files(model: dict[str, Any], degree: str, workdir: Path) -> None:
    data = workdir / "data"
    (data / "bachelor").mkdir(parents=True, exist_ok=True)
    (data / "master").mkdir(parents=True, exist_ok=True)
    (data / "com_info.tex").write_text(_com_info(model, degree), encoding="utf-8")
    (data / "abstract.tex").write_text(_abstracts(model), encoding="utf-8")
    (data / "body.tex").write_text(_body(model), encoding="utf-8")
    (data / "reference.tex").write_text(_references(model), encoding="utf-8")
    if degree == "undergraduate":
        (data / "bachelor" / "bachelor_info.tex").write_text(_bachelor_info(model), encoding="utf-8")
        (data / "bachelor" / "assign.tex").write_text(_assign(model), encoding="utf-8")
        (data / "bachelor" / "spine.tex").write_text(_spine_tex(model), encoding="utf-8")
        (data / "bachelor" / "assign_patch.tex").write_text(_assign_patch(model), encoding="utf-8")
        (data / "bachelor" / "acknowledgement.tex").write_text(_bachelor_ack(model), encoding="utf-8")
        (workdir / "thesis.tex").write_text(_main_undergraduate(), encoding="utf-8")
    else:
        (data / "master" / "master_info.tex").write_text(_master_info(model), encoding="utf-8")
        (data / "master" / "back2-acknowledgement.tex").write_text(_master_ack(model), encoding="utf-8")
        (data / "master" / "back3-aboutauthor.tex").write_text('% !Mode:: "TeX:UTF-8"\n\\chapter{作者简介}\n', encoding="utf-8")
        (workdir / "thesis.tex").write_text(_main_master(), encoding="utf-8")


def _main_undergraduate() -> str:
    return r"""% !Mode:: "TeX:UTF-8"
\documentclass[bachelor,openany,oneside,AutoFakeBold=true]{buaathesis}
\usepackage{gbt7714}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{adjustbox}
\usepackage{etoolbox}
\citestyle{numerical}
\begin{document}
\include{data/com_info}
\include{data/bachelor/bachelor_info}
\include{data/bachelor/assign}
\include{data/bachelor/spine}
\include{data/bachelor/assign_patch}
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


def _main_master() -> str:
    return r"""% !Mode:: "TeX:UTF-8"
\documentclass[master,openright,twoside,AutoFakeBold=true]{buaathesis}
\usepackage{gbt7714}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{adjustbox}
\citestyle{numerical}
\begin{document}
\include{data/com_info}
\include{data/master/master_info}
\maketitle
\pagestyle{frontmatter}
\include{data/abstract}
\tableofcontents
\mainmatter
\pagestyle{mainmatter}
\include{data/body}
\include{data/reference}
\backmatter
\include{data/master/back2-acknowledgement}
\include{data/master/back3-aboutauthor}
\end{document}
"""


def _com_info(model: dict[str, Any], degree: str) -> str:
    metadata = _metadata(model)
    title, subtitle = _title_pair(metadata.get("title_cn", ""))
    year, month, day = _date_parts(metadata.get("date", ""))
    if degree == "undergraduate":
        begin, end, defense, _fallback_fields = _task_book_date_parts(model)
    else:
        begin = end = defense = (year, month, day)
    empty = r"\mbox{}" if degree != "undergraduate" else " "
    school_value = (
        metadata.get("school_stem") or _buaa_macro_stem(metadata.get("college"), "学院")
        if degree == "undergraduate"
        else metadata.get("college")
    )
    major_value = (
        metadata.get("major_normalized") or _buaa_macro_stem(metadata.get("major"), "专业")
        if degree == "undergraduate"
        else metadata.get("major")
    )
    author_en = metadata.get("author_en") or empty
    tutor_en = metadata.get("tutor_en") or empty
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            rf"\school{{{tex_value(school_value, empty)}}}{{{empty}}}",
            rf"\major{{{tex_value(major_value, empty)}}}{{{empty}}}",
            r"\thesistitle",
            rf"{{{tex_value(title, empty)}}}",
            rf"{{{tex_value(subtitle, empty)}}}",
            rf"{{{tex_value(metadata.get('title_en'), empty)}}}",
            rf"{{{empty}}}",
            rf"\thesisauthor{{{tex_value(metadata.get('student_name'), empty)}}}{{{tex_value(author_en, empty)}}}",
            rf"\teacher{{{tex_value(metadata.get('advisor'), empty)}}}{{{tex_value(tutor_en, empty)}}}",
            rf"\category{{{tex_value(metadata.get('classification'), empty)}}}",
            rf"\thesisbegin{{{begin[0]}}}{{{begin[1]}}}{{{begin[2]}}}",
            rf"\thesisend{{{end[0]}}}{{{end[1]}}}{{{end[2]}}}",
            rf"\defense{{{defense[0]}}}{{{defense[1]}}}{{{defense[2]}}}",
            rf"\ckeyword{{{tex_escape('，'.join(_keywords(model.get('abstract_cn'))))}}}",
            rf"\ekeyword{{{tex_escape(', '.join(_keywords(model.get('abstract_en'))))}}}",
            "",
        ]
    )


def _bachelor_info(model: dict[str, Any]) -> str:
    metadata = _metadata(model)
    task = model.get("task_book") or {}
    year, month, _day = _date_parts(metadata.get("date", ""))
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            rf"\class{{{tex_value(task.get('class_name'), '')}}}",
            rf"\studentID{{{tex_value(metadata.get('student_id'), '')}}}",
            rf"\unicode{{{tex_value(metadata.get('unit_code') or '10006', '10006')}}}",
            rf"\thesisdate{{{year}}}{{{month}}}",
            "",
        ]
    )


def _spine_tex(model: dict[str, Any]) -> str:
    metadata = _metadata(model)
    title = _vertical_spine_text(metadata.get("title_cn"))
    author = _vertical_spine_text(metadata.get("student_name"))
    university = _vertical_spine_text("北京航空航天大学")
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            r"\makeatletter",
            r"\newcommand{\buaaSpinePage}{%",
            r"  \clearpage",
            r"  \thispagestyle{empty}%",
            r"  \begingroup",
            r"  \loadgeometry{bachelorgeometry}%",
            r"  \null\vfill",
            r"  \noindent\makebox[\textwidth][c]{%",
            r"    \begin{minipage}[t][0.80\textheight][t]{0.50\textwidth}",
            r"      \vspace*{0pt}\centering\heiti\zihao{3}\shortstack{" + title + r"}",
            r"    \end{minipage}\hfill",
            r"    \begin{minipage}[t][0.80\textheight][t]{0.16\textwidth}",
            r"      \vspace*{0pt}\centering\heiti\zihao{3}\shortstack{" + author + r"}",
            r"    \end{minipage}\hfill",
            r"    \begin{minipage}[t][0.80\textheight][t]{0.22\textwidth}",
            r"      \vspace*{0pt}\centering\heiti\zihao{3}\shortstack{" + university + r"}",
            r"    \end{minipage}%",
            r"  }%",
            r"  \vfill\null",
            r"  \endgroup",
            r"  \clearpage",
            r"}",
            r"\patchcmd{\maketitle}{\titlech}{\titlech\buaaSpinePage}{}{}",
            r"\makeatother",
            "",
        ]
    )


def _vertical_spine_text(value: Any) -> str:
    characters = [tex_escape(char) for char in str(value or "") if not char.isspace()]
    return r"\\".join(characters) if characters else r"\mbox{}"


def _master_info(model: dict[str, Any]) -> str:
    metadata = _metadata(model)
    year, month, day = _date_parts(metadata.get("date", ""))
    thesis_id = f"{metadata.get('unit_code') or '10006'}{metadata.get('student_id') or ''}"
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            r"\direction{\mbox{}}",
            r"\teacherdegree{\mbox{}}{\mbox{}}",
            r"\applydegree{\mbox{}}",
            rf"\thesisID{{{tex_escape(thesis_id)}}}",
            rf"\commit{{{year}}}{{{month}}}{{{day}}}",
            rf"\award{{{year}}}{{{month}}}{{{day}}}",
            "",
        ]
    )


def _assign(model: dict[str, Any]) -> str:
    task = model.get("task_book") or {}
    reflow_wrapped = model.get("source_type") == "pdf"
    raw_material_paragraphs = _assignment_paragraphs(task.get("raw_materials"), reflow_wrapped=reflow_wrapped)
    work_content_paragraphs = _assignment_paragraphs(task.get("work_content"), reflow_wrapped=reflow_wrapped)
    raw_material_lines = _assignment_text_lines(task.get("raw_materials"), width=ASSIGNMENT_TEXT_WIDTH)
    work_content_lines = _assignment_text_lines(task.get("work_content"), width=ASSIGNMENT_TEXT_WIDTH)
    raw_materials = _fixed_lines(raw_material_lines, 5)
    work_content = _fixed_lines(work_content_lines, 6)
    references = [item.get("raw", "") if isinstance(item, dict) else str(item) for item in task.get("references") or []]
    references = reference_render.assignment_reference_lines(references, 8)
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            _assignment_text_block_macro("buaaAssignReqBlock", raw_material_paragraphs, minimum_lines=6),
            _assignment_text_block_macro("buaaAssignWorkBlock", work_content_paragraphs, minimum_lines=7),
            reference_render.assignment_reference_block_macro(
                "buaaAssignRefBlock",
                [item.get("raw", "") if isinstance(item, dict) else str(item) for item in task.get("references") or []],
            ),
            _macro("assignReq", raw_materials),
            _macro("assignWork", work_content),
            _macro("assignRef", references, escape=False),
            "",
        ]
    )


def _assign_patch(model: dict[str, Any]) -> str:
    metadata = _metadata(model)
    lines = [
        '% !Mode:: "TeX:UTF-8"',
        r"\makeatletter",
        *_cover_title_spacing_patch(metadata),
        *_assign_first_page_spacing_patch(),
        r"\newcommand{\buaaAssignCollegeFull}{\buaa@school 学院}",
        r"\newcommand{\buaaAssignRuleFill}{\leaders\hrule height 0.4pt depth -0.1pt\hfill\kern0pt}",
        r"\newcommand{\buaaAssignTextParagraph}[1]{\par\noindent\uline{#1}\buaaAssignRuleFill\par}",
        r"\newcommand{\buaaAssignBlankLine}{\par\noindent\ulinel{}\par}",
        r"\newcommand{\buaaAssignRefParagraph}[1]{\par\noindent\uline{#1}\buaaAssignRuleFill\par}",
        *_assign_text_block_patch(
            [
                r"\ulinel{\buaa@bachelor@assign@req@one}",
                r"        \ulinel{\buaa@bachelor@assign@req@two}",
                r"        \ulinel{\buaa@bachelor@assign@req@three}",
                r"        \ulinel{\buaa@bachelor@assign@req@four}",
                r"        \ulinel{\buaa@bachelor@assign@req@five}",
            ],
            r"\buaaAssignReqBlock",
        ),
        *_assign_text_block_patch(
            [
                r"\ulinel{\buaa@bachelor@assign@work@one}",
                r"        \ulinel{\buaa@bachelor@assign@work@two}",
                r"        \ulinel{\buaa@bachelor@assign@work@three}",
                r"        \ulinel{\buaa@bachelor@assign@work@four}",
                r"        \ulinel{\buaa@bachelor@assign@work@five}",
                r"        \ulinel{\buaa@bachelor@assign@work@six}",
            ],
            r"\buaaAssignWorkBlock",
        ),
        *_assign_reference_patch(),
        *_assign_footer_patch(),
    ]
    if metadata.get("advisor"):
        lines.extend(
            [
                r"\patchcmd{\buaa@bachelor@assign}",
                r"{指导教师：\ulinec[.3]{}}",
                r"{指导教师：\ulinec[.3]{\buaa@teacher}}",
                r"{}{}",
            ]
        )
    lines.extend([r"\makeatother", ""])
    return "\n".join(lines)


def _cover_title_spacing_patch(metadata: dict[str, Any]) -> list[str]:
    return [
        rf"\newcommand{{\buaaCoverTitle}}{{{_cover_title_tex(metadata)}}}",
        r"\patchcmd{\titlech}",
        r"{\centering{\heiti\zihao{2}\buaa@thesistitle}}",
        r"{\begin{spacing}{1.5}\centering{\heiti\zihao{2}\buaaCoverTitle}\par\end{spacing}}",
        r"{}{}",
    ]


def _cover_title_tex(metadata: dict[str, Any]) -> str:
    lines = _cover_title_lines_from_metadata(metadata)
    if not lines:
        return r"\buaa@thesistitle"
    return r"\\[0.5\baselineskip]".join(tex_escape(line) for line in lines)


def _cover_title_lines_from_metadata(metadata: dict[str, Any]) -> list[str]:
    explicit = metadata.get("title_cn_lines") or metadata.get("cover_title_lines")
    if isinstance(explicit, list):
        lines = [str(line).strip() for line in explicit if str(line).strip()]
        if lines:
            return lines
    title = str(metadata.get("title_cn") or metadata.get("title_en") or "").strip()
    evidence = metadata.get("evidence") or {}
    title_evidence = evidence.get("title_cn") if isinstance(evidence, dict) else {}
    evidence_text = ""
    if isinstance(title_evidence, dict):
        evidence_text = str(title_evidence.get("evidence_text") or "").strip()
    if evidence_text and title.startswith(evidence_text):
        tail = title[len(evidence_text) :].strip()
        if tail:
            return [evidence_text, tail]
    return _cover_title_lines(title)


def _cover_title_lines(title: str) -> list[str]:
    explicit = [line.strip() for line in str(title or "").splitlines() if line.strip()]
    if len(explicit) > 1:
        return explicit
    if not explicit:
        return []
    value = explicit[0]
    if len(value) <= 18:
        return [value]
    for suffix in ("关键技术研究", "方法研究", "系统研究", "性能评估"):
        index = value.find(suffix)
        if 8 <= index <= len(value) - 4:
            return [value[:index].strip(), value[index:].strip()]
    split_at = min(18, max(10, len(value) // 2 + 2))
    if len(value) - split_at <= 2:
        split_at = max(1, len(value) - 6)
    return [value[:split_at].strip(), value[split_at:].strip()]


def _assign_first_page_spacing_patch() -> list[str]:
    return [
        r"\patchcmd{\buaa@bachelor@assign}",
        r"{\linespread{2}}",
        r"{\linespread{1.5}}",
        r"{}{}",
    ]


def _assign_text_block_patch(original_lines: list[str], replacement: str) -> list[str]:
    original = "\n".join(original_lines)
    return [r"\patchcmd{\buaa@bachelor@assign}", f"{{{original}}}", f"{{{replacement}}}", r"{}{}"]


def _assign_reference_patch() -> list[str]:
    original = "\n".join(
        [
            r"\ulinel{\buaa@bachelor@assign@ref@one}",
            r"        \ulinel{\buaa@bachelor@assign@ref@two}",
            r"        \ulinel{\buaa@bachelor@assign@ref@three}",
            r"        \ulinel{\buaa@bachelor@assign@ref@four}",
            r"        \ulinel{\buaa@bachelor@assign@ref@five}",
            r"        \ulinel{\buaa@bachelor@assign@ref@six}",
            r"        \ulinel{\buaa@bachelor@assign@ref@seven}",
            r"        \ulinel{\buaa@bachelor@assign@ref@eight}",
        ]
    )
    replacement = "\n".join(
        [
            r"\begingroup",
            r"        \zihao{-4}",
            r"\begin{spacing}{1.5}",
            r"        \setlength{\parindent}{0pt}",
            r"        \buaaAssignRefBlock",
            r"        \end{spacing}",
            r"\endgroup",
        ]
    )
    return [r"\patchcmd{\buaa@bachelor@assign}", f"{{{original}}}", f"{{{replacement}}}", r"{}{}"]


def _assign_footer_patch() -> list[str]:
    return [
        r"\patchcmd{\buaa@bachelor@assign}",
        r"{\ulinec[.28]{\buaa@school}学院\ulinec[.28]{\buaa@major}~专业类~\ulinec[.15]{\buaa@class}班 \\}",
        r"{\makebox[\textwidth][l]{\ulinec[.42]{\buaaAssignCollegeFull}\hspace{1em}\ulinec[.16]{\buaa@major}~专业类~\ulinec[.10]{\buaa@class}班}\\}",
        r"{}{}",
    ]


def _abstracts(model: dict[str, Any]) -> str:
    cn = model.get("abstract_cn") or {}
    en = model.get("abstract_en") or {}
    reflow_wrapped = model.get("source_type") == "pdf"
    blocks = ['% !Mode:: "TeX:UTF-8"', ""]
    if cn.get("body"):
        blocks.extend([r"\begin{cabstract}", _paragraphs(cn.get("body"), reflow_wrapped=reflow_wrapped), r"\end{cabstract}", ""])
    if en.get("body"):
        blocks.extend([r"\begin{eabstract}", _paragraphs(en.get("body"), reflow_wrapped=reflow_wrapped), r"\end{eabstract}", ""])
    return "\n".join(blocks)


def _body(model: dict[str, Any]) -> str:
    blocks = ['% !Mode:: "TeX:UTF-8"', ""]
    for item in model.get("body") or []:
        item_type = item.get("type")
        if item_type == "chapter":
            title = _heading_title(item)
            blocks.append(rf"\chapter{{{tex_escape(title)}}}")
        elif item_type == "section":
            blocks.append(rf"\section{{{tex_escape(_heading_title(item))}}}")
        elif item_type == "subsection":
            blocks.append(rf"\subsection{{{tex_escape(_heading_title(item))}}}")
        elif item_type == "paragraph":
            trace = item.get("source_trace") if isinstance(item.get("source_trace"), dict) else {}
            reflow_wrapped = trace.get("source_type") == "pdf" or model.get("source_type") == "pdf"
            blocks.append(_paragraphs(item.get("text"), reflow_wrapped=reflow_wrapped))
        elif item_type == "paragraph_mixed":
            blocks.append(_paragraph_mixed_block(item))
        elif item_type == "figure":
            blocks.append(_figure_block(item))
        elif item_type == "equation":
            blocks.append(equation_render.equation_block(item))
        elif item_type == "equation_preview":
            blocks.append(equation_render.equation_preview_block(item))
        elif item_type == "equation_placeholder":
            if item.get("insert_in_body"):
                blocks.append(r"\[\text{公式待复核}\]")
    if len(blocks) == 2:
        blocks.append(r"\chapter{绪论}")
    return "\n\n".join(blocks) + "\n"


def _figure_block(item: dict[str, Any]) -> str:
    caption = item.get("caption") or item.get("title") or ""
    render_asset = str(item.get("render_asset") or "")
    if render_asset:
        return "\n".join(
            [
                r"\begin{figure}[htbp]",
                r"\centering",
                rf"\adjustbox{{max width={FIGURE_MAX_WIDTH},max height={FIGURE_MAX_HEIGHT}}}{{\includegraphics{{{tex_escape(render_asset)}}}}}",
                rf"\caption{{{tex_escape(caption)}}}",
                r"\end{figure}",
            ]
        )
    return "\n".join(
        [
            r"\begin{figure}[htbp]",
            r"\centering",
            r"\fbox{图像缺失，需复核}",
            rf"\caption{{{tex_escape(caption)}}}",
            r"\end{figure}",
        ]
    )


def _paragraph_mixed_block(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for segment in item.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        segment_type = str(segment.get("type") or "")
        if segment_type == "text":
            parts.append(tex_escape(str(segment.get("text") or "")))
        elif segment_type == "equation_preview":
            parts.append(equation_render.inline_equation_preview(segment))
        elif segment_type == "equation":
            latex = str(segment.get("latex") or segment.get("text") or "").strip()
            if latex:
                parts.append(rf"\({latex}\)")
    return "".join(parts).strip()


def _references(model: dict[str, Any]) -> str:
    return reference_render.main_references_tex(model.get("references") or [])


def _bachelor_ack(model: dict[str, Any]) -> str:
    return "\n".join(
        [
            '% !Mode:: "TeX:UTF-8"',
            r"\chapter*{致谢}",
            r"\addcontentsline{toc}{chapter}{致谢}",
            _paragraphs(model.get("acknowledgement"), reflow_wrapped=model.get("source_type") == "pdf"),
            r"\cleardoublepage",
            "",
        ]
    )


def _master_ack(model: dict[str, Any]) -> str:
    return '% !Mode:: "TeX:UTF-8"\n\\chapter{致谢}\n' + _paragraphs(
        model.get("acknowledgement"), reflow_wrapped=model.get("source_type") == "pdf"
    ) + "\n"


def _report(
    model: dict[str, Any],
    degree: str,
    template_root: Path,
    inspection: dict[str, Any],
    public_tex: Path,
    out_dir: Path,
    compile_status: dict[str, Any],
) -> dict[str, Any]:
    metadata = _metadata(model)
    required = ["title_cn", "student_name", "student_id", "college", "major", "advisor", "date", "classification", "unit_code"]
    missing = [field for field in required if not metadata.get(field)]
    rendered_equations = _body_items_by_type(model.get("body") or [], "equation")
    preview_equations = _body_items_by_type(model.get("body") or [], "equation_preview")
    body_equations = [item for item in model.get("body") or [] if item.get("type") == "equation_placeholder"]
    review_equations = [item for item in model.get("equations_need_review") or [] if isinstance(item, dict)]
    equations = body_equations + review_equations
    figures = [item for item in model.get("body") or [] if item.get("type") == "figure"]
    missing_assets = _missing_assets(figures)
    unsupported_equations = [_unsupported_item(index, item, "equation_placeholder") for index, item in enumerate(equations)]
    unsupported_figures = [_unsupported_item(index, item, "figure") for index, item in enumerate(figures)]
    warnings = []
    if missing:
        warnings.append("missing metadata fields: " + ", ".join(missing))
    return {
        "template_used": inspection["template_path"],
        "degree_type": degree,
        "extracted_metadata": metadata,
        "missing_metadata": missing,
        "figures_extracted": len(figures),
        "figures_need_review": len([item for item in figures if item.get("needs_review")]),
        "equations_need_review": len(equations),
        "missing_assets": missing_assets,
        "unsupported_equations": unsupported_equations,
        "unsupported_figures": unsupported_figures,
        "references_count": len(model.get("references") or []),
        "task_book": _task_book_report(model),
        "metadata": _metadata_report(model),
        "figures": _figure_report(figures),
        "equations": equation_render.equation_report(equations, body_equations, rendered_equations, preview_equations),
        "references": {
            "taskbook_count": len((model.get("task_book") or {}).get("references") or []),
            "main_count": len(model.get("references") or []),
            "bad_wrapping_detected": reference_render.bad_reference_wrapping_detected(
                [*((model.get("task_book") or {}).get("references") or []), *(model.get("references") or [])]
            ),
        },
        "compile_status": compile_status,
        "warnings": warnings,
        "artifacts": {
            "template_path": str(template_root),
            "template_inspection": str(out_dir / "template_inspection.json"),
            "thesis_tex": str(public_tex),
            "thesis_pdf": str(out_dir / "thesis.pdf") if (out_dir / "thesis.pdf").exists() else "",
            "workdir": str(out_dir / "workdir"),
        },
    }


def _body_items_by_type(body: list[Any], item_type: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        if item.get("type") == item_type:
            items.append(item)
        for segment in item.get("segments") or []:
            if isinstance(segment, dict) and segment.get("type") == item_type:
                items.append(segment)
    return items


def _task_book_report(model: dict[str, Any]) -> dict[str, Any]:
    task = model.get("task_book") or {}
    _begin, _end, _defense, date_fallback_fields = _task_book_date_parts(model)
    bottom_fields = dict(task.get("bottom_fields") or {})
    if not bottom_fields:
        bottom_fields = {
            "college": task.get("college", ""),
            "major_class": task.get("major_class_display") or task.get("major_class", ""),
            "class_name": task.get("class_name", ""),
            "student_name": task.get("student_name", ""),
            "advisor": task.get("advisor", ""),
        }
    return {
        "missing_fields": list(task.get("missing_fields") or []),
        "fallback_fields": list(task.get("fallback_fields") or []),
        "references_count": len(task.get("references") or []),
        "advisor": task.get("advisor", ""),
        "college": task.get("college", ""),
        "major_class": task.get("major_class", ""),
        "date_range": task.get("date_range", ""),
        "defense_date": task.get("defense_date", ""),
        "date_fallback_fields": date_fallback_fields,
        "bottom_fields": {
            "college": bottom_fields.get("college", ""),
            "major_class": bottom_fields.get("major_class", ""),
            "class_name": bottom_fields.get("class_name", ""),
            "student_name": bottom_fields.get("student_name", ""),
            "advisor": bottom_fields.get("advisor", ""),
        },
    }


def _metadata_report(model: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(model)
    return {
        "college": metadata.get("college", ""),
        "major_raw": metadata.get("major_raw") or metadata.get("major", ""),
        "major_normalized": metadata.get("major_normalized") or metadata.get("major", ""),
        "major_display_for_taskbook": metadata.get("major_display_for_taskbook", ""),
        "class_name": metadata.get("class_name", ""),
        "advisor": metadata.get("advisor", ""),
    }


def _figure_report(figures: list[dict[str, Any]]) -> dict[str, Any]:
    bindings = [item for item in figures if item.get("render_asset")]
    needs_review = [_missing_figure_report_item(item) for item in figures if not item.get("render_asset")]
    return {
        "images_extracted": len(figures),
        "captions_detected": len(figures),
        "bindings": len(bindings),
        "missing": needs_review,
        "sizing_policy": {
            "method": "adjustbox_max_dimensions",
            "max_width": FIGURE_MAX_WIDTH,
            "max_height": FIGURE_MAX_HEIGHT,
            "upscale_small_images": False,
        },
        "needs_review": needs_review,
    }


def _missing_figure_report_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "number_hint": item.get("number_hint") or "",
        "caption": item.get("caption") or item.get("title") or "",
        "reason": item.get("missing_reason")
        or ("asset_missing" if not item.get("asset") and not item.get("asset_path") else "asset_missing_or_unsupported"),
    }


def _equation_report(
    equations: list[dict[str, Any]],
    body_equations: list[dict[str, Any]],
    rendered_equations: list[dict[str, Any]],
    preview_equations: list[dict[str, Any]],
) -> dict[str, Any]:
    ole_objects = [item for item in equations if "oleObject" in str(item.get("source_text") or item.get("id") or "")]
    return {
        "total": _equation_total(rendered_equations, preview_equations, body_equations, equations),
        "native_latex": len(rendered_equations),
        "image_fallback": len([item for item in preview_equations if item.get("render_asset")]),
        "placeholders": len(body_equations),
        "native_latex_complete": False if (preview_equations or equations or body_equations) else True,
        "conversion_tool": "none",
        "omml_converted": len([item for item in equations if item.get("kind") == "omml" and item.get("latex")]),
        "native_latex_rendered": len(rendered_equations),
        "equation_previews_rendered": len([item for item in preview_equations if item.get("render_asset")]),
        "ole_objects": len(ole_objects),
        "placeholders_inserted": len([item for item in body_equations if item.get("insert_in_body")]),
        "workflow": {
            "trusted_latex": "rendered_as_native_latex",
            "docx_omml_or_ole": "reported_for_review",
            "untrusted_or_missing_latex": "reported_for_review",
        },
        "needs_review": len(equations),
        "needs_review_items": equations,
    }


def _equation_total(
    rendered_equations: list[dict[str, Any]],
    preview_equations: list[dict[str, Any]],
    body_equations: list[dict[str, Any]],
    review_equations: list[dict[str, Any]],
) -> int:
    ids = {
        str(item.get("id"))
        for item in [*rendered_equations, *preview_equations, *body_equations, *review_equations]
        if item.get("id")
    }
    if ids:
        return len(ids)
    return len(rendered_equations) + len(preview_equations) + len(body_equations) + len(review_equations)


def _bad_reference_wrapping_detected(items: list[Any]) -> bool:
    for item in items:
        text = str(item.get("raw") if isinstance(item, dict) else item)
        if len(re.findall(r"\[\d+\]", text)) > 1:
            return True
        if re.search(r"[A-Z],(?=[A-Z][a-z])", text):
            return True
        if re.search(r"[a-z][A-Z](?=[\s.,;:])", text):
            return True
    return False


def _metadata(model: dict[str, Any]) -> dict[str, Any]:
    return dict(model.get("metadata") or {})


def _buaa_macro_stem(value: Any, suffix: str) -> str:
    text = str(value or "").strip()
    return text[: -len(suffix)] if suffix and text.endswith(suffix) else text


def _keywords(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    keywords = value.get("keywords") or []
    if isinstance(keywords, str):
        return [item.strip() for item in re.split(r"[;,，；]", keywords) if item.strip()]
    return [str(item) for item in keywords if str(item).strip()]


def _title_pair(title: str) -> tuple[str, str]:
    lines = [line.strip() for line in str(title or "").splitlines() if line.strip()]
    if len(lines) >= 2:
        return lines[0], " ".join(lines[1:])
    return (lines[0], "") if lines else ("", "")


def _date_parts(date: str) -> tuple[str, str, str]:
    parts = re.findall(r"\d+", str(date or ""))
    return (
        parts[0] if len(parts) > 0 else "",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
    )


TASK_BOOK_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{0,2})\s*月\s*(\d{0,2})\s*日")


def _task_book_date_parts(
    model: dict[str, Any],
) -> tuple[tuple[str, str, str], tuple[str, str, str], tuple[str, str, str], list[str]]:
    task = model.get("task_book") or {}
    date_range = TASK_BOOK_DATE_RE.findall(str(task.get("date_range") or ""))
    fallback_fields: list[str] = []
    if len(date_range) >= 2:
        begin, end = date_range[0], date_range[1]
    else:
        fallback = _date_parts((model.get("metadata") or {}).get("date", ""))
        begin = end = fallback
        fallback_fields.extend(["date_range.begin", "date_range.end"])
    defense_match = TASK_BOOK_DATE_RE.search(str(task.get("defense_date") or ""))
    defense = defense_match.groups() if defense_match else ("", "", "")
    return begin, end, defense, fallback_fields


def _lines(value: Any, count: int) -> list[str]:
    return _fixed_lines(_assignment_text_lines(value, width=ASSIGNMENT_TEXT_WIDTH), count)


def _fixed_lines(lines: list[str], count: int) -> list[str]:
    return (lines + [""] * count)[:count]


def _assignment_text_lines(value: Any, *, width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lines.extend(_wrap_display_line(line, width))
    return lines


def _wrap_cjk_line(value: str, width: int) -> list[str]:
    if len(value) <= width:
        return [value]
    chunks = []
    rest = value
    while rest:
        chunks.append(rest[:width].strip())
        rest = rest[width:].strip()
    return chunks


def _assignment_reference_lines(references: list[str], count: int) -> list[str]:
    lines = [str(reference or "").strip() for reference in references if str(reference or "").strip()]
    return [_assignment_reference_tex(line) for line in (lines + [""] * count)[:count]]


def _assignment_text_block_macro(name: str, paragraphs: list[str], *, minimum_lines: int) -> str:
    estimated_lines = sum(len(_wrap_display_line(paragraph, ASSIGNMENT_TEXT_WIDTH)) for paragraph in paragraphs)
    blank_lines = max(0, minimum_lines - estimated_lines)
    body = [rf"  \buaaAssignTextParagraph{{{tex_escape_with_cjk_breaks(paragraph)}}}" for paragraph in paragraphs]
    body.extend(r"  \buaaAssignBlankLine" for _ in range(blank_lines))
    return "\n".join(
        [
            rf"\newcommand{{\{name}}}{{%",
            r"  \begingroup\zihao{-4}\begin{spacing}{1.5}%",
            *body,
            r"  \end{spacing}\endgroup%",
            "}",
        ]
    )


def _assignment_paragraphs(value: Any, *, reflow_wrapped: bool = False) -> list[str]:
    if reflow_wrapped:
        return _reflow_pdf_paragraphs(value)
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _assignment_reference_block_macro(name: str, references: list[str]) -> str:
    lines = [str(reference or "").strip() for reference in references if str(reference or "").strip()]
    body = "\n".join(rf"  \buaaAssignRefTextLine{{{tex_escape(line)}}}" for line in lines)
    if not body:
        body = "  "
    return "\n".join([rf"\newcommand{{\{name}}}{{%", body, r"  \par\vspace{0.55em}%", "}"])


def _wrap_assignment_references(references: list[str], width: int) -> list[str]:
    lines: list[str] = []
    for reference in references:
        lines.extend(_wrap_display_line(str(reference or "").strip(), width))
    return [line for line in lines if line]


def _wrap_display_line(value: str, width: int) -> list[str]:
    if _display_width(value) <= width:
        return [value]
    lines: list[str] = []
    current = ""
    for token in re.split(r"(\s+)", value):
        if not token:
            continue
        candidate = f"{current}{token}" if current else token.lstrip()
        if _display_width(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current.strip())
            current = token.strip()
        else:
            current = token.strip()
        while _display_width(current) > width:
            head, current = _split_display_token(current, width)
            lines.append(head.strip())
    if current.strip():
        lines.append(current.strip())
    return lines


def _split_display_token(value: str, width: int) -> tuple[str, str]:
    total = 0
    for index, char in enumerate(value):
        total += 2 if _is_wide_char(char) else 1
        if total > width:
            return value[:index], value[index:]
    return value, ""


def _display_width(value: str) -> int:
    return sum(2 if _is_wide_char(char) else 1 for char in str(value or ""))


def _is_wide_char(char: str) -> bool:
    return "\u2e80" <= char <= "\uffff"


def _assignment_reference_tex(line: str) -> str:
    if not line:
        return ""
    return tex_escape(line)


def _macro(name: str, values: list[str], *, escape: bool = True) -> str:
    return "\n".join([rf"\{name}", *(rf"{{{tex_escape(value) if escape else value}}}" for value in values)])


def _paragraphs(value: Any, *, reflow_wrapped: bool = False) -> str:
    lines = _reflow_pdf_paragraphs(value) if reflow_wrapped else [
        line.strip() for line in str(value or "").splitlines() if line.strip()
    ]
    return "\n\n".join(tex_escape(line) for line in lines)


def _reflow_pdf_paragraphs(value: Any) -> list[str]:
    paragraphs: list[str] = []
    current = ""
    for raw_line in str(value or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue
        if current and _pdf_semantic_paragraph_start(line):
            paragraphs.append(current)
            current = line
        else:
            current = _join_pdf_physical_line(current, line)
    if current:
        paragraphs.append(current)
    return paragraphs


def _pdf_semantic_paragraph_start(line: str) -> bool:
    return bool(re.match(r"^(?:\d+[.、)]|[（(]\d+[）)])\s*\S", line))


def _join_pdf_physical_line(left: str, right: str) -> str:
    if not left:
        return right
    if left.endswith("-") and right[:1].islower():
        return left[:-1] + right
    if right[:1] in "，。；：！？、,.!?:;)]）":
        return left + right
    if _is_wide_char(left[-1]) or _is_wide_char(right[0]):
        return left + right
    return f"{left} {right}"


def _heading_title(item: dict[str, Any]) -> str:
    number = str(item.get("number") or "").strip()
    title = str(item.get("title") or "").strip()
    if title:
        if number:
            pattern = rf"^{re.escape(number)}(?:[\s.．、]+)(.+)$"
            match = re.match(pattern, title)
            if match:
                return match.group(1).strip()
        return title
    return number


def _missing_assets(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = []
    for index, item in enumerate(figures):
        source = item.get("asset_path") or item.get("source_path") or item.get("path")
        if source and not Path(str(source)).exists():
            missing.append({"index": index, "path": str(source), "reason": "asset_path_not_found"})
    return missing


def _unsupported_item(index: int, item: dict[str, Any], kind: str) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or f"{kind}-{index + 1}"),
        "index": index,
        "kind": kind,
        "reason": "not_converted_to_native_latex",
        "source_text": str(item.get("source_text") or item.get("text") or item.get("caption") or ""),
        "source_page": item.get("source_page"),
        "context": str(item.get("context") or ""),
        "source_path": str(item.get("asset_path") or item.get("source_path") or item.get("path") or ""),
    }
