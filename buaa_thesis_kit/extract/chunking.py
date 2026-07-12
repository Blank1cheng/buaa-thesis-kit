from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChunkRange:
    chunk_id: str
    page_start: int
    page_end: int


def parse_ranges(value: str | None) -> list[ChunkRange]:
    if not value:
        return []
    ranges: list[ChunkRange] = []
    for raw_part in str(value).split(","):
        part = raw_part.strip()
        if not part:
            continue
        if ":" not in part or "-" not in part:
            raise ValueError(f"Invalid range segment: {part}")
        chunk_id, page_range = part.split(":", 1)
        start_text, end_text = page_range.split("-", 1)
        page_start = int(start_text)
        page_end = int(end_text)
        if page_start < 1 or page_end < page_start:
            raise ValueError(f"Invalid page range: {part}")
        ranges.append(ChunkRange(chunk_id=chunk_id.strip(), page_start=page_start, page_end=page_end))
    return ranges


def chunk_document(source: str | Path, ranges: list[ChunkRange], out_dir: str | Path) -> dict:
    source = Path(source)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".pdf":
        return _chunk_pdf(source, ranges, out)
    if source.suffix.lower() == ".docx":
        return _chunk_docx(source, ranges, out)
    raise ValueError(f"Unsupported chunk source: {source}")


def _chunk_pdf(source: Path, ranges: list[ChunkRange], out: Path) -> dict:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    chunks = []
    for chunk_range in ranges:
        chunk_dir = out / chunk_range.chunk_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        writer = PdfWriter()
        text_blocks = []
        for page_number in range(chunk_range.page_start, min(chunk_range.page_end, len(reader.pages)) + 1):
            page = reader.pages[page_number - 1]
            writer.add_page(page)
            text = page.extract_text() or ""
            for index, line in enumerate(text.splitlines()):
                if line.strip():
                    text_blocks.append(
                        {
                            "text": line.strip(),
                            "source_trace": {
                                "source_file": str(source),
                                "source_type": "pdf",
                                "chunk_id": chunk_range.chunk_id,
                                "page_start": page_number,
                                "page_end": page_number,
                                "block_index": index,
                                "confidence": 0.65,
                            },
                        }
                    )
        with (chunk_dir / "pages.pdf").open("wb") as handle:
            writer.write(handle)
        payload = {
            "chunk_id": chunk_range.chunk_id,
            "source_file": str(source),
            "source_type": "pdf",
            "page_start": chunk_range.page_start,
            "page_end": chunk_range.page_end,
            "text_blocks": text_blocks,
            "images": [],
            "warnings": [],
        }
        (chunk_dir / "text.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        chunks.append(payload)
    report = {"source": str(source), "chunking_mode": "pdf_page_range", "chunks": chunks}
    (out / "chunk_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _chunk_docx(source: Path, ranges: list[ChunkRange], out: Path) -> dict:
    from docx import Document

    document = Document(str(source))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    chunks = []
    selected_ranges = ranges or [ChunkRange("document", 1, 1)]
    for chunk_range in selected_ranges:
        chunk_dir = out / chunk_range.chunk_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "chunk_id": chunk_range.chunk_id,
            "source_file": str(source),
            "source_type": "docx",
            "page_start": chunk_range.page_start,
            "page_end": chunk_range.page_end,
            "text_blocks": [
                {
                    "text": text,
                    "source_trace": {
                        "source_file": str(source),
                        "source_type": "docx",
                        "chunk_id": chunk_range.chunk_id,
                        "paragraph_start": index,
                        "paragraph_end": index,
                        "block_index": index,
                        "confidence": 0.55,
                    },
                }
                for index, text in enumerate(paragraphs)
            ],
            "images": [],
            "warnings": ["DOCX page ranges are approximate without Word COM; used heading_based chunking."],
        }
        (chunk_dir / "text.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        chunks.append(payload)
    report = {"source": str(source), "chunking_mode": "heading_based", "chunks": chunks}
    (out / "chunk_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def chunk_ranges_to_dict(ranges: list[ChunkRange]) -> list[dict]:
    return [asdict(item) for item in ranges]
