# BUAA Thesis Kit

Reusable BUAA undergraduate thesis formatting pipeline.

The pipeline accepts `.doc`, `.docx`, and `.pdf` thesis sources, extracts a reviewable thesis model, fills a reusable Word template, exports PDF from Word, emits an auxiliary TeX file, and keeps the public output directory small.

## Output Contract

Final output is intentionally restricted to:

```text
output/
  thesis.docx
  thesis.pdf
  thesis.tex
  report.md
  image/
```

Process files are written to a temporary work directory and removed by default. Use `--keep-work` only for debugging.

## Usage

```powershell
python buaa-thesis-kit/scripts/run_pipeline.py input.docx --out output
python buaa-thesis-kit/scripts/run_pipeline.py input.doc --out output
python buaa-thesis-kit/scripts/run_pipeline.py input.pdf --out output
python buaa-thesis-kit/scripts/run_pipeline.py input.docx --out output --keep-work
```

`thesis.docx` is the authoritative layout source. `thesis.pdf` is exported from `thesis.docx`. `thesis.tex` is an auxiliary structured backup for review and recovery.

## Input Handling

- DOC: converts to DOCX first with Word COM or LibreOffice, then uses the DOCX path below.
- DOCX: extracts metadata, sections, tables, references, images, and detectable formulas.
- Text PDF: extracts text and metadata heuristically, then marks layout review as required.
- Scanned/image PDF: renders page images into `output/image/` and marks OCR/manual transcription review as required.

The pipeline does not silently treat uncertain formulas, image placement, PDF text order, or OCR gaps as final quality. These appear in `report.md`.

## Report Status

- `pass`: all required outputs exist and no blocking/manual review items remain.
- `needs_review`: outputs exist, but formulas, images, references, metadata, PDF layout, or OCR require human confirmation.
- `failed`: extraction, template fill, or PDF export had a blocking failure.

## Verification

```powershell
python -m pytest buaa-thesis-kit/tests -q
python -m pytest generated/skill-tests/test_buaa_skills.py -q
python buaa-thesis-kit/scripts/build_template_assets.py
python buaa-thesis-kit/scripts/run_pipeline.py "论文\崔润昊毕设打印版.docx" --out generated\kit-final-output
python buaa-thesis-kit/scripts/run_pipeline.py "论文\20375284-宋郭睿-毕业论文.pdf" --out generated\kit-pdf-final-output
```

Then validate each output directory with `buaa_thesis_kit.validate.validate_clean_output`.
