# Phase 2 Roadmap

Phase 1 now supports DOCX and PDF inputs, clean output packaging, Word-authoritative PDF export, and conservative review reporting. Phase 2 should harden the remaining boundary cases:

- OCR engine integration with page-level confidence and an OCR ledger.
- MathType/OLE formula conversion to editable LaTeX or OMML with review packets.
- Figure/table caption reconciliation and cross-reference validation.
- GB/T 7714 reference normalization and citation-reference consistency checks.
- Visual regression for DOCX/PDF page margins, headers, footers, page numbers, and section starts.
- Golden-case suite for malformed theses, scanned PDFs, missing metadata, duplicate numbering, and corrupted images.
- Optional finalization mode that can fail on any `needs_review` item before submission.
