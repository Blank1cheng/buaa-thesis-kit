import importlib.util
from pathlib import Path
import re
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]

DOCX_TEMPLATE = ROOT / "templates" / "buaa_undergraduate_thesis_template.docx"
TEX_TEMPLATE = ROOT / "templates" / "buaa_undergraduate_thesis_template.tex"
BUILD_SCRIPT = ROOT / "scripts" / "build_template_assets.py"

REQUIRED_TEX_MACROS = (
    r"\newcommand{\BUAACoverTitle}",
    r"\newcommand{\BUAAChineseAbstract}",
    r"\newcommand{\BUAAEnglishAbstract}",
    r"\newcommand{\BUAATableOfContents}",
)

REFERENCE_DOCS = (
    "official-checklist.md",
    "template-field-map.md",
    "edge-cases.md",
    "agent-workflow.md",
)

REFERENCE_POLICY_TERMS = (
    "output/image",
    "人工复核",
    "公式",
    "元数据",
    "置信度",
    "证据",
    "Word 为权威源",
    "PDF 从 Word 导出",
)


def _load_template_builder():
    spec = importlib.util.spec_from_file_location("build_template_assets", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TEMPLATE_BUILDER = _load_template_builder()
MOJIBAKE_MARKERS = TEMPLATE_BUILDER.MOJIBAKE_MARKERS


def _write_docx_package(path, parts):
    with zipfile.ZipFile(path, "w") as package:
        for name, content in parts.items():
            package.writestr(name, content)


def _valid_docx_parts():
    return {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        ),
        "word/document.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body/>"
            "</w:document>"
        ),
        "word/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        ),
    }


def test_docx_template_is_valid_docx_package():
    assert DOCX_TEMPLATE.is_file()
    assert TEMPLATE_BUILDER._is_valid_docx(DOCX_TEMPLATE)

    with zipfile.ZipFile(DOCX_TEMPLATE) as package:
        assert "word/document.xml" in package.namelist()


def test_docx_template_has_no_static_header_or_footer_page_numbers():
    static_page_number = re.compile(r"第\s*(?:\d+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\s*页")

    with zipfile.ZipFile(DOCX_TEMPLATE) as package:
        for name in package.namelist():
            if not (name.startswith("word/header") or name.startswith("word/footer")):
                continue
            if not name.endswith(".xml"):
                continue
            xml = package.read(name).decode("utf-8", errors="replace")
            text = re.sub(r"<[^>]+>", "", xml)
            assert not static_page_number.search(text), name


def test_docx_validation_rejects_zip_with_only_document_xml(tmp_path):
    path = tmp_path / "only-document.docx"
    _write_docx_package(path, {"word/document.xml": "<w:document/>"})

    assert not TEMPLATE_BUILDER._is_valid_docx(path)


def test_docx_validation_rejects_malformed_xml(tmp_path):
    path = tmp_path / "malformed.docx"
    parts = _valid_docx_parts()
    parts["word/document.xml"] = "<w:document>"
    _write_docx_package(path, parts)

    assert not TEMPLATE_BUILDER._is_valid_docx(path)


def test_tex_template_contains_required_macros():
    assert TEX_TEMPLATE.is_file()

    tex = TEX_TEMPLATE.read_text(encoding="utf-8")
    for macro in REQUIRED_TEX_MACROS:
        assert macro in tex


def test_tex_template_has_no_obvious_mojibake():
    tex = TEX_TEMPLATE.read_text(encoding="utf-8")

    for marker in MOJIBAKE_MARKERS:
        assert marker not in tex


def test_mojibake_marker_list_includes_unicode_replacement_character():
    assert "�" in MOJIBAKE_MARKERS


def test_mojibake_marker_list_covers_common_old_template_markers():
    for marker in ("鎽", "榎", "瑕", "亇", "鑸", "锛"):
        assert marker in MOJIBAKE_MARKERS


def test_invalid_utf8_preferred_tex_source_falls_back(monkeypatch, tmp_path):
    bad_source = tmp_path / "bad-preferred.tex"
    output = tmp_path / "template.tex"
    macro_text = "\n".join(REQUIRED_TEX_MACROS).encode("ascii")
    bad_source.write_bytes(macro_text + b"\ninvalid-byte: \xff\n")

    monkeypatch.setattr(TEMPLATE_BUILDER, "PREFERRED_TEX_SOURCE", bad_source)
    monkeypatch.setattr(TEMPLATE_BUILDER, "TEX_TEMPLATE", output)

    TEMPLATE_BUILDER.build_tex_template()

    tex = output.read_text(encoding="utf-8")
    assert tex == TEMPLATE_BUILDER._minimal_xelatex_template()
    assert "�" not in tex


def test_tex_validation_accepts_current_and_fallback_templates():
    assert TEMPLATE_BUILDER._tex_is_reusable(TEX_TEMPLATE.read_text(encoding="utf-8"))
    assert TEMPLATE_BUILDER._tex_is_reusable(TEMPLATE_BUILDER._minimal_xelatex_template())


def test_tex_validation_rejects_macros_in_comments_only():
    commented_macros = "\n".join(f"% {macro}[1]{{}}" for macro in REQUIRED_TEX_MACROS)
    tex = (
        "\\documentclass{ctexrep}\n"
        f"{commented_macros}\n"
        "\\begin{document}\n"
        "CONTENT_PLACEHOLDER\n"
        "\\end{document}\n"
    )

    assert not TEMPLATE_BUILDER._tex_is_reusable(tex)


def test_tex_validation_rejects_incomplete_macro_declarations():
    incomplete_macros = "\n".join(REQUIRED_TEX_MACROS)
    tex = (
        "\\documentclass{ctexrep}\n"
        f"{incomplete_macros}\n"
        "\\begin{document}\n"
        "CONTENT_PLACEHOLDER\n"
        "\\end{document}\n"
    )

    assert not TEMPLATE_BUILDER._tex_is_reusable(tex)


def test_tex_validation_rejects_macros_only_after_end_document():
    trailing_macros = "\n".join(f"{macro}[1]{{body}}" for macro in REQUIRED_TEX_MACROS)
    tex = (
        "\\documentclass{ctexrep}\n"
        "\\begin{document}\n"
        "CONTENT_PLACEHOLDER\n"
        "\\end{document}\n"
        f"{trailing_macros}\n"
    )

    assert not TEMPLATE_BUILDER._tex_is_reusable(tex)


def test_tex_validation_rejects_placeholder_after_end_document():
    macro_defs = "\n".join(f"{macro}[1]{{body}}" for macro in REQUIRED_TEX_MACROS)
    tex = (
        "\\documentclass{ctexrep}\n"
        f"{macro_defs}\n"
        "\\begin{document}\n"
        "\\end{document}\n"
        "CONTENT_PLACEHOLDER\n"
    )

    assert not TEMPLATE_BUILDER._tex_is_reusable(tex)


def test_tex_validation_rejects_macros_only_after_placeholder():
    macro_defs = "\n".join(f"{macro}[1]{{body}}" for macro in REQUIRED_TEX_MACROS)
    tex = (
        "\\documentclass{ctexrep}\n"
        "\\begin{document}\n"
        "CONTENT_PLACEHOLDER\n"
        f"{macro_defs}\n"
        "\\end{document}\n"
    )

    assert not TEMPLATE_BUILDER._tex_is_reusable(tex)


def test_tex_validation_rejects_missing_required_structure():
    base = TEMPLATE_BUILDER._minimal_xelatex_template()

    assert not TEMPLATE_BUILDER._tex_is_reusable(base.replace("\\documentclass", "% \\documentclass"))
    assert not TEMPLATE_BUILDER._tex_is_reusable(base.replace("\\begin{document}", ""))
    assert not TEMPLATE_BUILDER._tex_is_reusable(base.replace("\\end{document}", ""))
    assert not TEMPLATE_BUILDER._tex_is_reusable(base.replace("CONTENT_PLACEHOLDER", ""))


def test_tex_validation_rejects_broader_mojibake_markers():
    tex = TEMPLATE_BUILDER._minimal_xelatex_template().replace("北京", "鑸")

    assert not TEMPLATE_BUILDER._tex_is_reusable(tex)


def test_source_path_overrides_prefer_cli_then_env(monkeypatch, tmp_path):
    env_docx = tmp_path / "env.docx"
    env_doc = tmp_path / "env.doc"
    env_tex = tmp_path / "env.tex"
    cli_docx = tmp_path / "cli.docx"
    cli_doc = tmp_path / "cli.doc"
    cli_tex = tmp_path / "cli.tex"

    monkeypatch.setenv("BUAA_TEMPLATE_DOCX_SOURCE", str(env_docx))
    monkeypatch.setenv("BUAA_TEMPLATE_DOC_SOURCE", str(env_doc))
    monkeypatch.setenv("BUAA_TEMPLATE_TEX_SOURCE", str(env_tex))

    env_sources = TEMPLATE_BUILDER.resolve_source_paths([])
    assert env_sources.preferred_docx == env_docx
    assert env_sources.legacy_doc == env_doc
    assert env_sources.preferred_tex == env_tex

    cli_sources = TEMPLATE_BUILDER.resolve_source_paths(
        [
            "--docx-source",
            str(cli_docx),
            "--doc-source",
            str(cli_doc),
            "--tex-source",
            str(cli_tex),
        ]
    )
    assert cli_sources.preferred_docx == cli_docx
    assert cli_sources.legacy_doc == cli_doc
    assert cli_sources.preferred_tex == cli_tex


def test_reference_docs_exist_and_cover_pipeline_policy():
    combined = []

    for name in REFERENCE_DOCS:
        path = ROOT / "references" / name
        assert path.is_file(), name
        combined.append(path.read_text(encoding="utf-8"))

    text = "\n".join(combined)
    for term in REFERENCE_POLICY_TERMS:
        assert term in text
