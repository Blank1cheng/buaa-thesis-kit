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


def _write_positioned_pdf(path: Path, pages: list[list[tuple[float, float, str, float]]]) -> None:
    document = fitz.open()
    for lines in pages:
        page = document.new_page(width=595, height=842)
        for x, y, text, size in lines:
            page.insert_text((x, y), text, fontsize=size)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def _valid_front_matter_pages() -> list[list[tuple[float, float, str, float]]]:
    return [
        [
            (180, 340, "Graduation Thesis", 36),
            (145, 450, "Template Conforming Thesis Title", 22),
            (145, 560, "College Name", 15),
            (145, 592, "Major Name", 15),
            (145, 623, "Student Name", 15),
            (145, 654, "Advisor Name", 15),
            (265, 715, "2026-06", 15),
        ],
        [(72, 72, "Book Spine", 12)],
        [(72, 72, "Declaration", 12)],
        [(72, 72, "Chinese Abstract", 12)],
        [(72, 72, "Abstract", 12)],
        [(72, 72, "1 Introduction", 12)],
    ]


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
    _write_positioned_pdf(pdf, _valid_front_matter_pages())

    result = inspect_pdf_output(pdf)

    assert result.blocking_items == []
    assert any("PDF layout validation passed" in note for note in result.notes)


def test_inspect_pdf_output_blocks_cover_geometry_outside_template_band(tmp_path):
    pdf = tmp_path / "bad-cover-geometry.pdf"
    pages = _valid_front_matter_pages()
    pages[0] = [
        (180, 90, "Graduation Thesis", 36),
        (145, 130, "Template Conforming Thesis Title", 22),
        (145, 170, "College Name", 15),
        (145, 200, "Student Name", 15),
        (265, 230, "2026-06", 15),
    ]
    _write_positioned_pdf(pdf, pages)

    result = inspect_pdf_output(pdf)

    assert any("pdf_cover_geometry" in item for item in result.blocking_items)
    assert result.notes == []
