from pathlib import Path

from buaa_thesis_kit.models import AssetItem, ContentBlock, EquationItem, Metadata, ThesisModel
from buaa_thesis_kit.tex_gen import generate_tex, tex_escape


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02\x00\x00\x00\x0bIDATx\xdac\xfc\xff"
    b"\x1f\x00\x03\x03\x02\x00\xef\xbf\xa7\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _sample_model(tmp_path: Path) -> ThesisModel:
    image_root = tmp_path / "assets"
    image_path = image_root / "figures" / "system.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(TINY_PNG)

    return ThesisModel(
        metadata=Metadata(
            title_cn="Data & Flight_控制",
            title_en="Data Driven Flight Control",
            student_name="Zhang San",
            advisor="Li Si",
        ),
        front_matter={
            "chinese_abstract": "中文摘要含 100% & 特殊字符。",
            "english_abstract": "English abstract with $value and #tag.",
            "keywords_cn": "控制；数据",
            "keywords_en": "control; data",
        },
        sections=[
            ContentBlock(
                id="sec-1",
                type="chapter",
                title="1 Introduction",
                text="Opening paragraph.\nSecond paragraph with {braces}.",
                level=1,
            ),
            ContentBlock(
                id="sec-2",
                type="section",
                title="1.1 Background",
                text="Background paragraph with A_B.",
                level=2,
            ),
            ContentBlock(
                id="sec-3",
                type="subsection",
                title="1.1.1 Detail",
                text="Detail paragraph.",
                level=3,
            ),
        ],
        tables=[
            ContentBlock(
                id="tbl-1",
                type="table",
                title="Table 1 Metrics",
                text="Metric\tValue\nAccuracy\t98%",
            )
        ],
        figures=[
            AssetItem(
                id="fig-1",
                type="image",
                path="figures/system.png",
                caption="Figure 1 System overview",
            )
        ],
        equations=[
            EquationItem(
                id="eq-tex",
                kind="latex",
                latex=r"E = mc^2",
                number="(1)",
                requires_review=False,
            ),
            EquationItem(id="eq-review", kind="omml", text="x+y", number="(2)", requires_review=True),
        ],
        references=[
            ContentBlock(id="ref-1", type="reference", text="[1] Wang. 100% flight_control study. 2026."),
            ContentBlock(id="ref-2", type="reference", text="[2] Smith & Jones. Data systems. 2025."),
        ],
        appendices=[
            ContentBlock(id="app-1", type="appendix", title="Appendix A", text="Supplemental material with #tag."),
        ],
    )


def test_tex_escape_special_chars_including_backslash_and_braces():
    assert tex_escape(r"\ & % $ # _ { } ~ ^") == (
        r"\textbackslash{} \& \% \$ \# \_ \{ \} \textasciitilde{} \textasciicircum{}"
    )


def test_default_template_replacement_keeps_macros_and_removes_placeholder(tmp_path):
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(_sample_model(tmp_path), output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert output.exists()
    assert r"\newcommand{\BUAACoverTitle}" in tex
    assert r"\BUAACoverTitle{Data \& Flight\_控制}" in tex
    assert r"\BUAAChineseAbstract{Zhang San}{Li Si}" in tex
    assert r"\BUAAEnglishAbstract{Zhang San}{Li Si}" in tex
    assert r"\BUAATableOfContents" in tex
    assert "CONTENT_PLACEHOLDER" not in tex


def test_renders_sections_table_figure_equations_references_and_appendices(tmp_path):
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(_sample_model(tmp_path), output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert r"\chapter{1 Introduction}" in tex
    assert "Opening paragraph." in tex
    assert r"Second paragraph with \{braces\}." in tex
    assert r"\section{1.1 Background}" in tex
    assert r"\subsection{1.1.1 Detail}" in tex
    assert r"\begin{tabular}" in tex
    assert r"Metric & Value \\" in tex
    assert r"Accuracy & 98\% \\" in tex
    assert r"\includegraphics" in tex
    assert "../assets/figures/system.png" in tex
    assert r"\caption{Figure 1 System overview}" in tex
    assert "% Equation number: (1)" in tex
    assert r"\[E = mc^2\]" in tex
    assert "% REVIEW: equation eq-review (omml) requires manual TeX transcription" in tex
    assert "% REVIEW: equation text: x+y" in tex
    assert "% REVIEW: equation number: (2)" in tex
    assert r"\chapter*{References}" in tex or r"\chapter*{参考文献}" in tex
    assert r"[1] Wang. 100\% flight\_control study. 2026." in tex
    assert r"[2] Smith \& Jones. Data systems. 2025." in tex
    assert r"\appendix" in tex
    assert r"\chapter{Appendix A}" in tex
    assert r"Supplemental material with \#tag." in tex


def test_missing_image_produces_review_comment_and_does_not_fail(tmp_path):
    model = _sample_model(tmp_path)
    model.figures = [
        AssetItem(
            id="fig-missing",
            type="image",
            path="figures/missing.png",
            caption="Missing figure",
        )
    ]
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(model, output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert "% REVIEW: figure fig-missing missing or unsupported image" in tex
    assert "% REVIEW: figure caption: Missing figure" in tex
    assert "% REVIEW: figure path: figures/missing.png" in tex
    assert r"\includegraphics[width=0.8\textwidth]{figures/missing.png}" not in tex


def test_trusted_latex_equation_renders_final_display_math_with_number(tmp_path):
    model = _sample_model(tmp_path)
    model.equations = [
        EquationItem(
            id="eq-trusted",
            kind="latex",
            latex=r"F = ma",
            number="(3)",
            requires_review=False,
        )
    ]
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(model, output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert "% Equation number: (3)" in tex
    assert r"\[F = ma\]" in tex
    assert r"\tag{3}" not in tex
    assert "% REVIEW: equation eq-trusted" not in tex


def test_reviewed_latex_equation_keeps_review_marker_near_rendered_latex(tmp_path):
    model = _sample_model(tmp_path)
    model.equations = [
        EquationItem(
            id="eq-reviewed-latex",
            kind="latex",
            latex=r"a=b",
            number="(7)",
            requires_review=True,
        )
    ]
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(model, output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert "% REVIEW: equation eq-reviewed-latex (latex) requires review before final TeX" in tex
    assert "% Equation number: (7)" in tex
    assert r"\[a=b\]" in tex
    assert r"\tag{7}" not in tex


def test_latex_equation_environment_is_not_mutated_for_numbering(tmp_path):
    latex = "\\begin{equation*}\na=b\n\\end{equation*}"
    model = _sample_model(tmp_path)
    model.equations = [
        EquationItem(
            id="eq-star",
            kind="latex",
            latex=latex,
            number="(8)",
            requires_review=False,
        )
    ]
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(model, output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert "% Equation number: (8)" in tex
    assert latex in tex
    assert r"\tag{8}" not in tex


def test_latex_align_environment_is_not_mutated_for_numbering(tmp_path):
    latex = "\\begin{align}\na&=b\\\\\nc&=d\n\\end{align}"
    model = _sample_model(tmp_path)
    model.equations = [
        EquationItem(
            id="eq-align",
            kind="latex",
            latex=latex,
            number="(9)",
            requires_review=False,
        )
    ]
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(model, output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert "% Equation number: (9)" in tex
    assert latex in tex
    assert r"\tag{9}" not in tex


def test_reviewed_existing_figure_includes_review_marker_near_graphics(tmp_path):
    image_path = tmp_path / "assets" / "figures" / "review.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(TINY_PNG)
    model = _sample_model(tmp_path)
    model.figures = [
        AssetItem(
            id="fig-review",
            type="image",
            path="figures/review.png",
            caption="Needs visual review",
            requires_review=True,
        )
    ]
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(model, output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert "% REVIEW: figure fig-review requires review before final TeX" in tex
    assert r"\includegraphics[width=0.8\textwidth]{../assets/figures/review.png}" in tex
    assert r"\caption{Needs visual review}" in tex


def test_absolute_missing_image_path_is_sanitized_in_review_comment(tmp_path):
    absolute_missing = tmp_path / "private" / "missing-secret.png"
    model = _sample_model(tmp_path)
    model.figures = [
        AssetItem(
            id="fig-abs-missing",
            type="image",
            path=str(absolute_missing),
            caption="Absolute missing figure",
        )
    ]
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(model, output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert str(absolute_missing) not in tex
    assert str(absolute_missing).replace("\\", "/") not in tex
    assert absolute_missing.parent.name not in tex
    if absolute_missing.drive:
        assert absolute_missing.drive not in tex
    assert "% REVIEW: figure path: missing-secret.png" in tex


def test_posix_absolute_missing_image_path_is_sanitized_on_windows(tmp_path):
    posix_missing = "/tmp/private/missing-secret.png"
    model = _sample_model(tmp_path)
    model.figures = [
        AssetItem(
            id="fig-posix-missing",
            type="image",
            path=posix_missing,
            caption="POSIX missing figure",
        )
    ]
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(model, output, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert posix_missing not in tex
    assert "/tmp/private" not in tex
    assert "% REVIEW: figure path: missing-secret.png" in tex


def test_creates_only_requested_tex_file_in_output_directory(tmp_path):
    output_dir = tmp_path / "empty-output"
    output = output_dir / "thesis.tex"

    generate_tex(_sample_model(tmp_path), output, image_root=tmp_path / "assets")

    assert sorted(path.name for path in output_dir.iterdir()) == ["thesis.tex"]


def test_minimal_fallback_has_no_obvious_unreplaced_placeholders(tmp_path):
    template = tmp_path / "invalid-template.tex"
    template.write_text(r"\begin{document}NO_PLACEHOLDER\end{document}", encoding="utf-8")
    output = tmp_path / "out" / "thesis.tex"

    generate_tex(_sample_model(tmp_path), output, template_path=template, image_root=tmp_path / "assets")

    tex = output.read_text(encoding="utf-8")
    assert r"\documentclass" in tex
    assert r"\begin{document}" in tex
    assert "CONTENT_PLACEHOLDER" not in tex
    assert "{{" not in tex
    assert "}}" not in tex
    assert "NO_PLACEHOLDER" not in tex
