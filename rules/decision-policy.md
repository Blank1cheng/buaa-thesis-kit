# Decision Policy

The pipeline may automatically fix deterministic formatting issues. It must not guess academic content.

## Status

- `pass`: all required outputs exist and no blocking or manual-review items remain.
- `needs_review`: outputs can be generated, but at least one formula, image, table, reference, or metadata field needs human confirmation.
- `failed`: a required section, required metadata field, Word export, or critical parse step failed.

## Required Blocking Cases

- Conflicting high-confidence title, student name, or student id.
- Missing references section.
- Unreadable formula object with no preview.
- DOCX output not created.
- PDF not exported from DOCX.
- Final output contains process files outside `image/`.

## Manual Review Cases

- Low-confidence metadata.
- Missing acknowledgements.
- MathType/OLE formula retained without verified LaTeX.
- Image equation.
- Figure caption and image match below confidence threshold.
- Reference entry not normalized to GB/T 7714.
