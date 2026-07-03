from pathlib import Path

import fitz

from buaa_thesis_kit.pdf_acceptance import inspect_pdf_output


def _write_marker_pdf(path: Path, pages: list[list[str]]) -> None:
    document = fitz.open()
    for lines in pages:
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 72), "\n".join(lines), fontsize=12)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def test_inspect_pdf_output_blocks_collapsed_front_matter_pages(tmp_path):
    pdf = tmp_path / "collapsed.pdf"
    _write_marker_pdf(
        pdf,
        [
            [
                "Graduation Thesis",
                "Book Spine",
                "Declaration",
                "Chinese Abstract",
                "Abstract",
                "1 Introduction",
            ]
        ],
    )

    result = inspect_pdf_output(pdf)

    assert any("pdf_layout_collapsed" in item for item in result.blocking_items)
    assert result.notes == []


def test_inspect_pdf_output_accepts_separated_front_matter_pages(tmp_path):
    pdf = tmp_path / "separated.pdf"
    _write_marker_pdf(
        pdf,
        [
            ["Graduation Thesis", "Thesis title"],
            ["Book Spine", "Thesis title"],
            ["Declaration", "Declaration body."],
            ["Chinese Abstract", "Chinese abstract body."],
            ["Abstract", "English abstract body."],
            ["1 Introduction", "Body text."],
        ],
    )

    result = inspect_pdf_output(pdf)

    assert result.blocking_items == []
    assert any("PDF layout validation passed" in note for note in result.notes)
