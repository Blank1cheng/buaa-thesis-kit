# Phase 2 Roadmap

Phase 1 now supports DOCX and PDF inputs, clean output packaging, Word-authoritative PDF export, editable Word auditing, and conservative review reporting. Phase 1.1 also includes strict finalization mode through `--strict`, where unresolved review items produce `strict_finalization_failed`. Phase 2 should harden the remaining boundary cases:

- OCR quality hardening beyond the current optional engine hook: language packs, confidence calibration, and layout-aware paragraph reconstruction.
- MathType/OLE formula conversion beyond the current `Equation Ledger`, including automatic editable LaTeX/OMML recovery and review packets.
- Figure/table caption reconciliation and cross-reference validation.
- GB/T 7714 reference normalization and citation-reference consistency checks.
- Visual regression for DOCX/PDF page margins, headers, footers, page numbers, and section starts.
- Golden-case suite for malformed theses, scanned PDFs, missing metadata, duplicate numbering, and corrupted images.
- Golden-case strict finalization fixtures across DOC, DOCX, text-PDF, and scanned-PDF inputs.
