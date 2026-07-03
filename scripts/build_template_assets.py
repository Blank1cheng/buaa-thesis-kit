from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


KIT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = KIT_ROOT.parent
TEMPLATES_DIR = KIT_ROOT / "templates"

DOCX_TEMPLATE = TEMPLATES_DIR / "buaa_undergraduate_thesis_template.docx"
TEX_TEMPLATE = TEMPLATES_DIR / "buaa_undergraduate_thesis_template.tex"

PREFERRED_DOCX_SOURCE = (
    WORKSPACE_ROOT / "generated" / "analysis" / "附件1-北航本科论文模板.converted.docx"
)
LEGACY_DOC_SOURCE = WORKSPACE_ROOT / "格式要求" / "附件1-北航本科论文模板.doc"
PREFERRED_TEX_SOURCE = (
    WORKSPACE_ROOT
    / "generated"
    / "skills"
    / "buaa-undergraduate-format-fix"
    / "assets"
    / "buaa-undergraduate-thesis-template.tex"
)

REQUIRED_TEX_MACROS = (
    r"\newcommand{\BUAACoverTitle}",
    r"\newcommand{\BUAAChineseAbstract}",
    r"\newcommand{\BUAAEnglishAbstract}",
    r"\newcommand{\BUAATableOfContents}",
)

REQUIRED_TEX_MACRO_NAMES = (
    "BUAACoverTitle",
    "BUAAChineseAbstract",
    "BUAAEnglishAbstract",
    "BUAATableOfContents",
)

REQUIRED_DOCX_XML_PARTS = (
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/styles.xml",
)
WORDPROCESSINGML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

MOJIBAKE_MARKERS = (
    "鍖",
    "绗",
    "椤",
    "姣",
    "烘枃",
    "鎽",
    "榎",
    "瑕",
    "亇",
    "鑸",
    "锛",
    "�",
    "ï¿½",
)


@dataclass(frozen=True)
class TemplateSources:
    preferred_docx: Path
    legacy_doc: Path
    preferred_tex: Path


class TemplateAssetError(RuntimeError):
    """Raised when required template assets cannot be produced safely."""


def _is_valid_docx(path: Path) -> bool:
    try:
        if not path.is_file() or not zipfile.is_zipfile(path):
            return False

        with zipfile.ZipFile(path) as package:
            names = set(package.namelist())
            if any(part not in names for part in REQUIRED_DOCX_XML_PARTS):
                return False

            for part in REQUIRED_DOCX_XML_PARTS:
                ET.fromstring(package.read(part))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError, UnicodeDecodeError):
        return False

    return True


def _copy_valid_docx(source: Path, destination: Path) -> None:
    if not _is_valid_docx(source):
        raise TemplateAssetError(f"DOCX 模板源无效或损坏：{source}")

    shutil.copy2(source, destination)


def _is_header_footer_xml(name: str) -> bool:
    return (
        name.startswith("word/header") or name.startswith("word/footer")
    ) and name.endswith(".xml")


def _empty_header_footer_part(name: str) -> bytes:
    tag = "ftr" if Path(name).name.startswith("footer") else "hdr"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:{tag} xmlns:w="{WORDPROCESSINGML_NS}"/>'
    ).encode("utf-8")


def _sanitize_docx_template(path: Path) -> None:
    if not _is_valid_docx(path):
        raise TemplateAssetError(f"DOCX template is invalid before sanitizing: {path}")

    with tempfile.NamedTemporaryFile(
        prefix=f"{path.stem}-", suffix=".docx", dir=path.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)

    try:
        with zipfile.ZipFile(path, "r") as source_package, zipfile.ZipFile(
            temp_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as sanitized_package:
            for info in source_package.infolist():
                data = source_package.read(info.filename)
                if _is_header_footer_xml(info.filename):
                    data = _empty_header_footer_part(info.filename)
                sanitized_package.writestr(info, data)
        if not _is_valid_docx(temp_path):
            raise TemplateAssetError(f"Sanitized DOCX template is invalid: {temp_path}")
        shutil.move(str(temp_path), str(path))
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _find_soffice() -> str | None:
    candidates = [
        "soffice",
        "soffice.exe",
        "libreoffice",
        "libreoffice.exe",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]

    for env_name in ("SOFFICE", "LIBREOFFICE"):
        env_value = shutil.os.environ.get(env_name)
        if env_value and Path(env_value).is_file():
            return env_value

    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found

    return None


def _convert_legacy_doc_to_docx(
    source: Path, destination: Path, preferred_docx_source: Path | None = None
) -> None:
    preferred_docx_source = preferred_docx_source or PREFERRED_DOCX_SOURCE
    soffice = _find_soffice()
    if not soffice:
        raise TemplateAssetError(
            "找不到可用 DOCX 模板源。请先生成 "
            f"{preferred_docx_source}，或安装 LibreOffice/soffice 后再从 "
            f"{source} 转换。"
        )

    with tempfile.TemporaryDirectory(prefix="buaa-thesis-template-") as tmp:
        tmp_dir = Path(tmp)
        result = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                str(tmp_dir),
                str(source),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        converted = tmp_dir / f"{source.stem}.docx"

        if result.returncode != 0 or not _is_valid_docx(converted):
            details = (result.stderr or result.stdout or "").strip()
            raise TemplateAssetError(
                "LibreOffice 转换 DOC 模板失败。请手动生成 "
                f"{preferred_docx_source} 后重试。{details}"
            )

        shutil.copy2(converted, destination)


def build_docx_template(
    preferred_docx_source: Path | None = None, legacy_doc_source: Path | None = None
) -> None:
    preferred_docx_source = preferred_docx_source or PREFERRED_DOCX_SOURCE
    legacy_doc_source = legacy_doc_source or LEGACY_DOC_SOURCE

    if preferred_docx_source.is_file():
        _copy_valid_docx(preferred_docx_source, DOCX_TEMPLATE)
        _sanitize_docx_template(DOCX_TEMPLATE)
        print(f"wrote {DOCX_TEMPLATE} from {preferred_docx_source}")
        return

    if legacy_doc_source.is_file():
        _convert_legacy_doc_to_docx(
            legacy_doc_source, DOCX_TEMPLATE, preferred_docx_source
        )
        _sanitize_docx_template(DOCX_TEMPLATE)
        print(f"wrote {DOCX_TEMPLATE} from converted {legacy_doc_source}")
        return

    raise TemplateAssetError(
        "缺少 Word 模板源。请提供 "
        f"{preferred_docx_source}，或提供 {legacy_doc_source} 并安装 LibreOffice。"
    )


def _strip_tex_comments(content: str) -> str:
    active_lines = []

    for line in content.splitlines():
        chars = []
        backslash_count = 0
        for char in line:
            if char == "%" and backslash_count % 2 == 0:
                break
            chars.append(char)
            if char == "\\":
                backslash_count += 1
            else:
                backslash_count = 0
        active_lines.append("".join(chars))

    return "\n".join(active_lines)


def _has_active_newcommand(active_content: str, macro_name: str) -> bool:
    pattern = re.compile(
        rf"\\(?:re)?newcommand\s*"
        rf"\{{\s*\\{re.escape(macro_name)}\s*\}}\s*"
        rf"(?:\[\s*\d+\s*\]\s*)?"
        rf"\{{[\s\S]*?\}}"
    )
    return bool(pattern.search(active_content))


def _tex_is_reusable(content: str) -> bool:
    if any(marker in content for marker in MOJIBAKE_MARKERS):
        return False

    active_content = _strip_tex_comments(content)
    if not re.search(r"\\documentclass(?:\[[^\]]*\])?\s*\{[^}]+\}", active_content):
        return False

    begin_at = active_content.find(r"\begin{document}")
    end_at = active_content.find(r"\end{document}")
    if begin_at == -1 or end_at == -1 or begin_at > end_at:
        return False

    body_content = active_content[begin_at:end_at]
    placeholder_at = body_content.find("CONTENT_PLACEHOLDER")
    if placeholder_at == -1:
        return False

    validation_content = active_content[: begin_at + placeholder_at]
    return all(
        _has_active_newcommand(validation_content, name)
        for name in REQUIRED_TEX_MACRO_NAMES
    )


def _minimal_xelatex_template() -> str:
    return r"""\documentclass[UTF8,a4paper,12pt]{ctexrep}
\usepackage{geometry}
\usepackage{fontspec}
\usepackage{graphicx}
\usepackage{caption}
\usepackage{booktabs}
\usepackage{array}
\usepackage{hyperref}

\geometry{top=30mm,bottom=25mm,left=30mm,right=20mm}
\IfFontExistsTF{Times New Roman}{\setmainfont{Times New Roman}}{}
\IfFontExistsTF{SimSun}{\setCJKmainfont{SimSun}}{}
\IfFontExistsTF{SimHei}{\setCJKsansfont{SimHei}}{}
\graphicspath{{image/}{output/image/}}

\captionsetup[figure]{font=small,labelfont=normalfont,position=bottom,labelsep=space}
\captionsetup[table]{font=small,labelfont=bf,position=top,labelsep=space}
\hypersetup{hidelinks}

\newcommand{\BUAACoverTitle}[1]{%
  \begin{titlepage}
  \centering
  {\zihao{2}\heiti 北京航空航天大学本科毕业设计（论文）\par}
  \vspace{18mm}
  {\zihao{3}\heiti #1\par}
  \vfill
  \end{titlepage}
}

\newcommand{\BUAACoverInfoField}[2]{%
  \par\noindent\makebox[30mm][r]{#1：}\underline{\makebox[90mm][c]{#2}}\par
}

\newcommand{\BUAAChineseAbstract}[4]{%
  \chapter*{摘\quad 要}
  \addcontentsline{toc}{chapter}{摘要}
  \noindent 学生：#1\quad 指导教师：#2\par
  \vspace{\baselineskip}
  #3\par
  \vspace{\baselineskip}
  \noindent{\heiti 关键词：}#4\par
}

\newcommand{\BUAAEnglishAbstract}[4]{%
  \chapter*{Abstract}
  \addcontentsline{toc}{chapter}{Abstract}
  \noindent Author: #1\quad Supervisor: #2\par
  \vspace{\baselineskip}
  #3\par
  \vspace{\baselineskip}
  \noindent\textbf{Key Words: }#4\par
}

\newcommand{\BUAATableOfContents}{%
  \clearpage
  \tableofcontents
  \clearpage
}

\begin{document}
% 使用 Word 作为权威排版源；本 TeX 文件作为结构化备份模板。
% 图片相对路径采用 output/image 或同目录 image。
CONTENT_PLACEHOLDER
\end{document}
"""


def build_tex_template(preferred_tex_source: Path | None = None) -> None:
    preferred_tex_source = preferred_tex_source or PREFERRED_TEX_SOURCE

    if preferred_tex_source.is_file():
        try:
            source_content = preferred_tex_source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            source_content = None

        if source_content is not None and _tex_is_reusable(source_content):
            TEX_TEMPLATE.write_text(source_content, encoding="utf-8", newline="\n")
            print(f"wrote {TEX_TEMPLATE} from {preferred_tex_source}")
            return

    TEX_TEMPLATE.write_text(_minimal_xelatex_template(), encoding="utf-8", newline="\n")
    print(f"wrote clean minimal XeLaTeX template to {TEX_TEMPLATE}")


def _override_path(cli_value: str | None, env_name: str, default: Path) -> Path:
    value = cli_value or os.environ.get(env_name)
    return Path(value) if value else default


def resolve_source_paths(argv: list[str] | None = None) -> TemplateSources:
    parser = argparse.ArgumentParser(
        description="Build reusable BUAA undergraduate thesis template assets."
    )
    parser.add_argument(
        "--docx-source",
        help="Preferred converted DOCX template source. Overrides BUAA_TEMPLATE_DOCX_SOURCE.",
    )
    parser.add_argument(
        "--doc-source",
        help="Legacy DOC template source. Overrides BUAA_TEMPLATE_DOC_SOURCE.",
    )
    parser.add_argument(
        "--tex-source",
        help="Preferred TeX template source. Overrides BUAA_TEMPLATE_TEX_SOURCE.",
    )
    args = parser.parse_args(argv)

    return TemplateSources(
        preferred_docx=_override_path(
            args.docx_source, "BUAA_TEMPLATE_DOCX_SOURCE", PREFERRED_DOCX_SOURCE
        ),
        legacy_doc=_override_path(
            args.doc_source, "BUAA_TEMPLATE_DOC_SOURCE", LEGACY_DOC_SOURCE
        ),
        preferred_tex=_override_path(
            args.tex_source, "BUAA_TEMPLATE_TEX_SOURCE", PREFERRED_TEX_SOURCE
        ),
    )


def main(argv: list[str] | None = None) -> int:
    sources = resolve_source_paths(argv)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    build_docx_template(sources.preferred_docx, sources.legacy_doc)
    build_tex_template(sources.preferred_tex)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TemplateAssetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
