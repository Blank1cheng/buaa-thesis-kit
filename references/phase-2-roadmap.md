# Phase 2 Roadmap

Phase 1 now supports DOCX and PDF inputs, layout-aware PDF text-line extraction, clean output packaging, Word-authoritative PDF export, editable Word auditing, official-template in-place filling, and conservative review reporting. Phase 1.1 also includes strict finalization mode through `--strict`, where unresolved review items produce `strict_finalization_failed`. Phase 2 should harden the remaining boundary cases:

- OCR quality hardening beyond the current optional engine hook: language packs, confidence calibration, and layout-aware paragraph reconstruction for scanned pages.
- MathType/OLE formula conversion beyond the current `Equation Ledger`, including automatic editable LaTeX/OMML recovery and review packets.
- Figure/table caption reconciliation beyond the current numbering/cross-reference gate and DOCX nearest-caption binding, including complex table structure recovery, merged cells, grouped figures, and layout placement checks.
- GB/T 7714 reference normalization and citation-reference consistency checks.
- Visual regression for DOCX/PDF page margins, headers, footers, page numbers, and section starts.
- Golden official-template fixtures that compare the instrumented template copy against reference DOCX/PDF page geometry for cover logo positions, title line breaks, vertical spine placement, task book I/II/III/IV blocks, declaration signature fields, abstract headers, TOC page numbers, and body page-number restart. Treat `buaa_thesis_kit/frontmatter_render/` as legacy/debug-only unless explicitly reworking fallback behavior; the main path must keep using `assemble_in_place.py` and `template_inheritance_report.json`.
- Section-recovery fixtures for DOCX auto-numbered headings, split PDF headings, chapter-summary paragraphs, and heading/page-break false positives.
- Word-body contamination fixtures that block debug markers, local asset paths, image filenames, English `References` headings, and equation token dumps from appearing as final editable body text.
- Golden-case suite for malformed theses, scanned PDFs, missing metadata, duplicate numbering, and corrupted images.
- Golden-case strict finalization fixtures across DOC, DOCX, text-PDF, and scanned-PDF inputs.
