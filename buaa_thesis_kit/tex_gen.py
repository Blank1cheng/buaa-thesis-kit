from __future__ import annotations

import os
import re
from pathlib import Path
from pathlib import PurePosixPath
from pathlib import PureWindowsPath
from typing import Iterable

from buaa_thesis_kit.models import AssetItem, ContentBlock, EquationItem, ThesisModel


CONTENT_PLACEHOLDER = "CONTENT_PLACEHOLDER"
DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "templates" / "buaa_undergraduate_thesis_template.tex"
)
SUPPORTED_IMAGE_SUFFIXES = {".bmp", ".eps", ".jpg", ".jpeg", ".pdf", ".png", ".tif", ".tiff"}
OCR_EVIDENCE_FIGURE_TYPES = {"pdf-page-image"}

FALLBACK_TEMPLATE = r"""\documentclass[UTF8,a4paper,12pt]{ctexrep}
\usepackage{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{array}
\usepackage{hyperref}

\geometry{top=30mm,bottom=25mm,left=30mm,right=20mm}

\begin{document}
CONTENT_PLACEHOLDER
\end{document}
"""

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


def generate_tex(
    model: ThesisModel,
    output_path: Path,
    template_path: Path | None = None,
    image_root: Path | None = None,
) -> None:
    """Render an auxiliary XeLaTeX thesis file from a ThesisModel."""
    output_path = Path(output_path)
    template = _load_template(template_path)
    body = _render_body(model, template, output_path.parent, image_root)
    tex = template.replace(CONTENT_PLACEHOLDER, body)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tex, encoding="utf-8")


def tex_escape(text: str) -> str:
    """Escape ordinary text for TeX."""
    return "".join(_TEX_ESCAPE_MAP.get(char, char) for char in str(text))


def _load_template(template_path: Path | None) -> str:
    candidate = Path(template_path) if template_path is not None else DEFAULT_TEMPLATE
    if candidate.exists():
        text = candidate.read_text(encoding="utf-8")
        if CONTENT_PLACEHOLDER in text:
            return text
    return FALLBACK_TEMPLATE


def _render_body(
    model: ThesisModel,
    template: str,
    output_parent: Path,
    image_root: Path | None,
) -> str:
    blocks: list[str] = []
    blocks.extend(_render_metadata_and_front_matter(model, template))
    blocks.extend(_render_sections(model.sections))
    blocks.extend(_render_tables(model.tables))
    blocks.extend(_render_figures(model.figures, output_parent, image_root))
    blocks.extend(_render_equations(model.equations))
    blocks.extend(_render_references(model.references))
    blocks.extend(_render_appendices(model.appendices))
    return "\n\n".join(block for block in blocks if block).rstrip() + "\n"


def _render_metadata_and_front_matter(model: ThesisModel, template: str) -> list[str]:
    metadata = model.metadata
    title = metadata.title_cn or metadata.title_en or "Untitled Thesis"
    blocks = [_render_title(title, template)]
    blocks.extend(_render_metadata_fields(model, template))

    chinese_abstract = _front_matter_value(
        model,
        "chinese_abstract",
        "abstract_cn",
        "cn_abstract",
    )
    english_abstract = _front_matter_value(
        model,
        "english_abstract",
        "abstract_en",
        "en_abstract",
    )
    if chinese_abstract:
        blocks.append(
            _render_abstract(
                template=template,
                macro_name="BUAAChineseAbstract",
                fallback_heading="Chinese Abstract",
                author=metadata.student_name,
                advisor=metadata.advisor,
                abstract=chinese_abstract,
                keywords=_front_matter_value(
                    model,
                    "keywords_cn",
                    "chinese_keywords",
                    "cn_keywords",
                    "keywords",
                ),
            )
        )
    if english_abstract:
        blocks.append(
            _render_abstract(
                template=template,
                macro_name="BUAAEnglishAbstract",
                fallback_heading="English Abstract",
                author=metadata.student_name,
                advisor=metadata.advisor,
                abstract=english_abstract,
                keywords=_front_matter_value(
                    model,
                    "keywords_en",
                    "english_keywords",
                    "en_keywords",
                    "keywords",
                ),
            )
        )

    if _macro_exists(template, "BUAATableOfContents"):
        blocks.append(r"\BUAATableOfContents")
    else:
        blocks.append("\\tableofcontents\n\\clearpage")
    return blocks


def _render_title(title: str, template: str) -> str:
    escaped_title = tex_escape(title)
    if _macro_exists(template, "BUAACoverTitle"):
        return rf"\BUAACoverTitle{{{escaped_title}}}"
    return "\\begin{center}\n" rf"{{\LARGE\bfseries {escaped_title}}}" "\n\\end{center}"


def _render_metadata_fields(model: ThesisModel, template: str) -> list[str]:
    metadata = model.metadata
    fields = [
        ("Student Name", metadata.student_name),
        ("Student ID", metadata.student_id),
        ("College", metadata.college),
        ("Major", metadata.major),
        ("Advisor", metadata.advisor),
        ("Date", metadata.date),
        ("Classification", metadata.classification),
        ("Unit Code", metadata.unit_code),
    ]
    present_fields = [(label, value) for label, value in fields if value]
    if not present_fields:
        return []

    if _macro_exists(template, "BUAACoverInfoField"):
        return [
            rf"\BUAACoverInfoField{{{tex_escape(label)}}}{{{tex_escape(value)}}}"
            for label, value in present_fields
        ]

    lines = ["\\begin{center}", "\\begin{tabular}{ll}"]
    lines.extend(
        rf"{tex_escape(label)} & {tex_escape(value)} \\"
        for label, value in present_fields
    )
    lines.extend(["\\end{tabular}", "\\end{center}"])
    return ["\n".join(lines)]


def _render_abstract(
    *,
    template: str,
    macro_name: str,
    fallback_heading: str,
    author: str,
    advisor: str,
    abstract: str,
    keywords: str,
) -> str:
    if _macro_exists(template, macro_name):
        return (
            rf"\{macro_name}"
            rf"{{{tex_escape(author)}}}"
            rf"{{{tex_escape(advisor)}}}"
            rf"{{{tex_escape(abstract)}}}"
            rf"{{{tex_escape(keywords)}}}"
        )

    blocks = [rf"\chapter*{{{tex_escape(fallback_heading)}}}"]
    blocks.extend(_render_text_paragraphs(abstract))
    if keywords:
        blocks.append(rf"\noindent\textbf{{Keywords: }}{tex_escape(keywords)}")
    return "\n\n".join(blocks)


def _render_sections(sections: Iterable[ContentBlock]) -> list[str]:
    blocks: list[str] = []
    for section in sections:
        if section.title:
            command = _section_command(section)
            blocks.append(rf"\{command}{{{tex_escape(section.title)}}}")
        blocks.extend(_render_text_paragraphs(section.text))
    return blocks


def _render_tables(tables: Iterable[ContentBlock]) -> list[str]:
    blocks: list[str] = []
    for table in tables:
        rows = _parse_table_rows(table.text)
        if not rows:
            if table.title:
                blocks.append(rf"\paragraph{{{tex_escape(table.title)}}}")
            blocks.extend(_render_text_paragraphs(table.text))
            continue

        column_count = max(len(row) for row in rows)
        lines = ["\\begin{table}[htbp]", "\\centering"]
        if table.title:
            lines.append(rf"\caption{{{tex_escape(table.title)}}}")
        lines.append(rf"\begin{{tabular}}{{{'l' * column_count}}}")
        for row in rows:
            padded = row + [""] * (column_count - len(row))
            cells = " & ".join(tex_escape(cell) for cell in padded)
            lines.append(rf"{cells} \\")
        lines.extend(["\\end{tabular}", "\\end{table}"])
        blocks.append("\n".join(lines))
    return blocks


def _render_figures(
    figures: Iterable[AssetItem],
    output_parent: Path,
    image_root: Path | None,
) -> list[str]:
    blocks: list[str] = []
    for figure in figures:
        if _is_ocr_evidence_figure(figure):
            blocks.append(_ocr_evidence_review_comment(figure, image_root))
            continue
        image_path = _resolve_image_path(figure, output_parent, image_root)
        if image_path is None:
            blocks.append(_figure_review_comment(figure, image_root))
            continue

        include_path = _tex_include_path(image_path, output_parent, image_root)
        lines = [
            "\\begin{figure}[htbp]",
            "\\centering",
            rf"\includegraphics[width=0.8\textwidth]{{{include_path}}}",
        ]
        if figure.requires_review:
            lines.insert(0, f"% REVIEW: figure {figure.id} requires review before final TeX")
        if figure.caption:
            lines.append(rf"\caption{{{tex_escape(figure.caption)}}}")
        lines.append("\\end{figure}")
        blocks.append("\n".join(lines))
    return blocks


def _render_equations(equations: Iterable[EquationItem]) -> list[str]:
    blocks: list[str] = []
    for equation in equations:
        latex = equation.latex.strip()
        if latex:
            rendered = _display_equation(latex)
            if equation.number:
                rendered = "\n".join([_equation_number_comment(equation.number), rendered])
            if equation.requires_review:
                blocks.append(
                    "\n".join(
                        [
                            f"% REVIEW: equation {equation.id} ({equation.kind}) requires review before final TeX",
                            rendered,
                        ]
                    )
                )
            else:
                blocks.append(rendered)
        else:
            blocks.append(_equation_review_comment(equation))
    return blocks


def _render_references(references: Iterable[ContentBlock]) -> list[str]:
    rendered_references: list[str] = []
    for reference in references:
        text = reference.text or reference.title
        rendered_references.extend(_render_text_paragraphs(text))
    if not rendered_references:
        return []
    return [
        "\n\n".join(
            [
                r"\chapter*{References}",
                r"\addcontentsline{toc}{chapter}{References}",
                *rendered_references,
            ]
        )
    ]


def _render_appendices(appendices: Iterable[ContentBlock]) -> list[str]:
    appendices = list(appendices)
    if not appendices:
        return []
    return [r"\appendix", *_render_sections(appendices)]


def _front_matter_value(model: ThesisModel, *keys: str) -> str:
    for key in keys:
        value = model.front_matter.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(str(item) for item in value if item)
    return ""


def _macro_exists(template: str, macro_name: str) -> bool:
    return rf"\{macro_name}" in template


def _render_text_paragraphs(text: str) -> list[str]:
    return [tex_escape(line.strip()) for line in str(text or "").splitlines() if line.strip()]


def _parse_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        rows.append([cell.strip() for cell in line.split("\t")])
    return rows


def _section_command(section: ContentBlock) -> str:
    block_type = section.type.lower()
    if block_type in {"chapter", "section", "subsection"}:
        return block_type
    if section.level <= 1:
        return "chapter"
    if section.level == 2:
        return "section"
    return "subsection"


def _resolve_image_path(
    figure: AssetItem,
    output_parent: Path,
    image_root: Path | None,
) -> Path | None:
    if not figure.path:
        return None

    raw_path = Path(figure.path)
    candidates = _image_candidates(raw_path, output_parent, image_root)
    for candidate in candidates:
        if _is_supported_existing_image(candidate):
            return candidate.resolve(strict=False)
    return None


def _image_candidates(
    raw_path: Path,
    output_parent: Path,
    image_root: Path | None,
) -> list[Path]:
    candidates: list[Path] = []
    if image_root is not None:
        root = Path(image_root)
        if raw_path.is_absolute():
            if _is_relative_to(raw_path, root):
                candidates.append(raw_path)
            candidates.append(root / raw_path.name)
        else:
            candidates.append(root / raw_path)
            if raw_path.name != str(raw_path):
                candidates.append(root / raw_path.name)

    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(output_parent / raw_path)
        candidates.append(raw_path)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _is_supported_existing_image(path: Path) -> bool:
    return path.exists() and path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES


def _is_ocr_evidence_figure(figure: AssetItem) -> bool:
    return str(figure.type or "").strip().lower() in OCR_EVIDENCE_FIGURE_TYPES


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _tex_include_path(path: Path, output_parent: Path, image_root: Path | None) -> str:
    resolved_path = path.resolve(strict=False)
    try:
        relative = os.path.relpath(
            resolved_path,
            output_parent.resolve(strict=False),
        )
    except ValueError:
        if image_root is not None and _is_relative_to(resolved_path, Path(image_root)):
            relative = str(resolved_path.relative_to(Path(image_root).resolve(strict=False)))
        else:
            relative = resolved_path.name
    if Path(relative).is_absolute():
        relative = Path(relative).name
    return _tex_path(relative)


def _display_equation(latex: str) -> str:
    stripped = latex.strip()
    if _is_standalone_math(stripped):
        return stripped
    return "\\[" + stripped + "\\]"


def _is_standalone_math(latex: str) -> bool:
    return (
        latex.startswith(r"\[")
        or latex.startswith("$$")
        or latex.startswith(r"\begin{")
        or (latex.startswith("$") and latex.endswith("$"))
    )


def _equation_number_comment(number: str) -> str:
    return f"% Equation number: {_comment_value(number)}"


def _figure_review_comment(figure: AssetItem, image_root: Path | None) -> str:
    comments = [f"% REVIEW: figure {figure.id} missing or unsupported image"]
    if figure.caption:
        comments.append(f"% REVIEW: figure caption: {_comment_value(figure.caption)}")
    if figure.path:
        comments.append(f"% REVIEW: figure path: {_comment_value(_sanitized_path(figure.path, image_root))}")
    return "\n".join(comments)


def _ocr_evidence_review_comment(figure: AssetItem, image_root: Path | None) -> str:
    comments = [f"% REVIEW: OCR evidence page image {figure.id} requires transcription; not included as a final figure"]
    if figure.caption:
        comments.append(f"% REVIEW: OCR evidence caption: {_comment_value(figure.caption)}")
    if figure.path:
        comments.append(f"% REVIEW: OCR evidence path: {_comment_value(_sanitized_path(figure.path, image_root))}")
    return "\n".join(comments)


def _equation_review_comment(equation: EquationItem) -> str:
    comments = [
        f"% REVIEW: equation {equation.id} ({equation.kind}) requires manual TeX transcription"
    ]
    if equation.text:
        comments.append(f"% REVIEW: equation text: {_comment_value(equation.text)}")
    if equation.number:
        comments.append(f"% REVIEW: equation number: {_comment_value(equation.number)}")
    if equation.preview_path:
        comments.append(
            f"% REVIEW: equation preview: {_comment_value(_sanitized_path(equation.preview_path, None))}"
        )
    return "\n".join(comments)


def _comment_value(value: str) -> str:
    return tex_escape(" ".join(str(value).splitlines()))


def _sanitized_path(value: str, image_root: Path | None) -> str:
    if _looks_like_absolute_path(value):
        path = Path(value)
        if image_root is not None and _is_relative_to(path, Path(image_root)):
            return _tex_path(str(path.resolve(strict=False).relative_to(Path(image_root).resolve(strict=False))))
        return _path_basename(value)
    return _tex_path(str(value))


def _tex_path(value: str) -> str:
    return str(value).replace("\\", "/")


def _looks_like_absolute_path(value: str) -> bool:
    text = str(value)
    return (
        Path(text).is_absolute()
        or PurePosixPath(text).is_absolute()
        or PureWindowsPath(text).is_absolute()
    )


def _path_basename(value: str) -> str:
    parts = [part for part in re.split(r"[\\/]+", str(value).strip()) if part]
    if not parts:
        return ""
    return parts[-1]


__all__ = ["generate_tex", "tex_escape"]
