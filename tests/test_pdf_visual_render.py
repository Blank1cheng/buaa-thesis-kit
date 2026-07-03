import re
import zipfile
from pathlib import Path

from pypdf import PdfWriter

from buaa_thesis_kit.pdf_visual_render import render_pdf_pages_as_docx


def _write_blank_pdf(path: Path, pages: int = 1) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def test_pdf_page_images_are_slightly_smaller_than_page_to_avoid_word_overflow(tmp_path):
    source = tmp_path / "source.pdf"
    output = tmp_path / "visual.docx"
    _write_blank_pdf(source)

    render_pdf_pages_as_docx(source, output, tmp_path / "work")

    with zipfile.ZipFile(output) as docx_zip:
        document_xml = docx_zip.read("word/document.xml").decode("utf-8")

    page_size = re.search(r'<w:pgSz w:w="(?P<w>\d+)" w:h="(?P<h>\d+)"', document_xml)
    image_extent = re.search(r'<wp:extent cx="(?P<cx>\d+)" cy="(?P<cy>\d+)"', document_xml)
    assert page_size is not None
    assert image_extent is not None

    page_width_inches = int(page_size.group("w")) / 1440
    page_height_inches = int(page_size.group("h")) / 1440
    image_width_inches = int(image_extent.group("cx")) / 914400
    image_height_inches = int(image_extent.group("cy")) / 914400

    assert image_width_inches < page_width_inches
    assert image_height_inches < page_height_inches
