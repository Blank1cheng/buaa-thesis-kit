import base64
from pathlib import Path

from docx import Document

from buaa_thesis_kit.editable_template_render import render_editable_buaa_docx
from buaa_thesis_kit.models import ContentBlock, Metadata, ThesisModel
from buaa_thesis_kit.docx_acceptance import inspect_docx_output


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "buaa_undergraduate_thesis_template.docx"
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _write_image_only_docx(path: Path) -> None:
    image = path.with_suffix(".png")
    image.write_bytes(TINY_PNG)
    document = Document()
    document.add_picture(str(image))
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def test_inspect_docx_output_blocks_pdf_word_without_editable_text(tmp_path):
    output = tmp_path / "image-only.docx"
    _write_image_only_docx(output)

    result = inspect_docx_output(
        output,
        Metadata(title_cn="PDF Pipeline Thesis", student_id="20370001"),
        source_kind="pdf",
        require_spine=False,
    )

    assert any("editable_text_missing" in item for item in result.blocking_items)


def test_inspect_docx_output_blocks_docx_word_without_editable_text(tmp_path):
    output = tmp_path / "image-only.docx"
    _write_image_only_docx(output)

    result = inspect_docx_output(
        output,
        Metadata(title_cn="Editable Thesis", student_id="20370001"),
        source_kind="docx",
        require_spine=False,
    )

    assert any("editable_text_missing" in item for item in result.blocking_items)


def test_inspect_docx_output_blocks_equation_preview_screenshot_substitute(tmp_path):
    output = tmp_path / "equation-preview.docx"
    document = Document()
    document.add_paragraph("Editable Thesis")
    document.add_paragraph("20370001")
    document.add_paragraph("[Equation preview inserted] equation.bin")
    document.save(output)

    result = inspect_docx_output(
        output,
        Metadata(title_cn="Editable Thesis", student_id="20370001"),
        source_kind="docx",
        require_spine=False,
    )

    assert any("editable_equation_missing" in item for item in result.blocking_items)


def test_inspect_docx_output_blocks_internal_equation_object_token(tmp_path):
    output = tmp_path / "equation-token.docx"
    document = Document()
    document.add_paragraph("Editable Thesis")
    document.add_paragraph("20370001")
    document.add_paragraph("__BUAA_EDITABLE_EQUATION_OBJECT__buaa-equation-eq-1__")
    document.save(output)

    result = inspect_docx_output(
        output,
        Metadata(title_cn="Editable Thesis", student_id="20370001"),
        source_kind="docx",
        require_spine=False,
    )

    assert any("editable_equation_object_token_visible" in item for item in result.blocking_items)


def test_inspect_docx_output_accepts_editable_template_word(tmp_path):
    output = tmp_path / "editable.docx"
    model = ThesisModel(
        metadata=Metadata(
            title_cn="PDF Pipeline Thesis",
            student_id="20370001",
            student_name="Zhang San",
            college="Automation College",
            major="Automation",
            advisor="Li Si",
            date="2026年7月",
            classification="TN953",
        ),
        sections=[
            ContentBlock(
                id="section-1",
                type="section",
                title="1 Introduction",
                text="This PDF contains extractable thesis text.",
            )
        ],
    )
    render_editable_buaa_docx(TEMPLATE, model, output)

    result = inspect_docx_output(
        output,
        model.metadata,
        source_kind="pdf",
        require_spine=True,
    )

    assert result.blocking_items == []
    assert any("editable Word validation passed" in note for note in result.notes)
