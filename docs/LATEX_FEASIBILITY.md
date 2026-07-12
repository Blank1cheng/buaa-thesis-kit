# BUAA LaTeX Feasibility Spike

## Goal

Evaluate a parallel LaTeX rendering path for BUAA thesis PDF output. The flow
is split into two profiles:

- `bachelor`: undergraduate thesis, matching the BHOSC undergraduate sample.
- `master`: graduate thesis, matching the BHOSC master sample.

This does not replace the editable Word pipeline and does not hide any Word
harness failures.

The source of truth is still `model.json`. The LaTeX renderer does not OCR
missing content and does not invent missing metadata, figures, equations,
references, or abstracts.

## Template Investigation

### BHOSC/BUAAthesis

Repository: <https://github.com/BHOSC/BUAAthesis>

This is the closest resource for this spike. It includes a `bachelor` class
option, `sample-bachelor.tex`, undergraduate cover/front-matter logic in
`buaathesis.cls`, and reusable Beihang cover assets under `figure/`. Its README
states that the project is a BUAA thesis LaTeX template and publishes a compiled
undergraduate sample PDF.

The default renderer now uses a BHOSC-backed project layout. It copies
`buaathesis.cls`, the GB/T 7714 support files, and the `figure/` assets into the
output directory, then writes `data/*.tex` files from `model.json`. This is much
closer to `sample-bachelor.tex` and `sample-master.tex` than the earlier
lightweight imitation.

## Current Pivot: Template Fill, Not Cover Reconstruction

The active LaTeX path uses BUAAthesis' own cover and front-matter
implementation. The renderer must not manually create a LaTeX `titlepage`,
manual cover table, or hand-positioned Beihang logo/wordmark. It only fills the
variables expected by BUAAthesis and calls `\maketitle`.

Local template pointer:

- `templates/external/BUAAthesis` points to the local BHOSC/BUAAthesis clone.
- If missing, clone with:

```powershell
git clone https://github.com/BHOSC/BUAAthesis templates/external/BUAAthesis
```

Undergraduate entrypoint and metadata API are inspected from the upstream
template:

- Entry file: `sample-bachelor.tex`
- Class file: `buaathesis.cls`
- Metadata files written by this project:
  - `data/com_info.tex`
  - `data/bachelor/bachelor_info.tex`
  - `data/bachelor/assign.tex`
  - `data/abstract.tex`
  - `data/body.tex`
  - `data/reference.tex`

Key BUAAthesis metadata macros:

- `\school{cn}{en}`
- `\major{cn}{en}`
- `\thesistitle{cn_title}{cn_subtitle}{en_title}{en_subtitle}`
- `\thesisauthor{cn}{en}`
- `\teacher{cn}{en}`
- `\category{classification}`
- `\studentID{id}`
- `\unicode{unit_code}`
- `\thesisdate{year}{month}`
- `\ckeyword{keywords}`
- `\ekeyword{keywords}`

Current commands:

```powershell
python scripts/inspect_buaa_template.py --buaa-template-path templates/external/BUAAthesis --degree-type undergraduate --out output/latex_pipeline_inspect_external
python scripts/render_buaa_latex.py --empty-demo --buaa-template-path templates/external/BUAAthesis --degree-type undergraduate --out output/latex_pipeline_empty_demo_external
python scripts/validate_extraction.py output/latex_pipeline/model.json --source tests/fixtures/truncated_input.docx --sample-mode truncated --out output/latex_pipeline/harness
python scripts/run_latex_pipeline.py tests/fixtures/truncated_input.docx --buaa-template-path templates/external/BUAAthesis --degree-type undergraduate --out output/latex_pipeline --sample-mode truncated
python scripts/chunk_document.py input.pdf --ranges frontmatter:1-8,body:9-30,references:31-33 --out output/chunks
python scripts/cleanup_legacy_artifacts.py --dry-run
```

Current generated artifacts:

- `output/latex_pipeline/model.json`
- `output/latex_pipeline/thesis.tex`
- `output/latex_pipeline/thesis.pdf`
- `output/latex_pipeline/compile.log`
- `output/latex_pipeline/report.json`
- `output/latex_pipeline/template_inspection.json`
- `output/latex_pipeline/harness/extraction_gate_board.json`
- `output/latex_pipeline/harness/extraction_failure_queue.json`
- `output/latex_pipeline/harness/metadata_report.json`
- `output/latex_pipeline/harness/gate_board.json`
- `output/latex_pipeline/harness/failure_queue.json`
- `output/latex_pipeline/debug/*.json`
- `output/latex_pipeline/debug/pages/page-*.png`

Current extraction behavior:

- The pipeline always writes `model.json` before rendering.
- The extraction harness runs before LaTeX render.
- Required undergraduate metadata missing from extraction blocks LaTeX render
  unless `--allow-extraction-fail` is passed.
- `needs_review` extraction gates may continue to render, but the final report
  keeps `status=needs_review`.
- Metadata extraction now supports label/value rows, spaced Chinese labels, and
  cover-position inference for the truncated sample.
- Chunking support is available for named PDF page ranges and approximate DOCX
  chunks; missing traceability is currently `needs_review`.

### yzd-v/BUAA_thesis_overleaf

Repository: <https://github.com/yzd-v/BUAA_thesis_overleaf>

This appears to be an Overleaf-oriented BUAA thesis variant. It remains a
candidate for later comparison, especially if the team wants an Overleaf-native
workflow. It was not used as the primary source for this first spike because
BHOSC already exposes the undergraduate sample and class structure locally.

### Overleaf BUAA Thesis Template Clean

Overleaf template page: <https://www.overleaf.com/latex/templates>

This is useful as an Overleaf packaging reference, especially for dependency
layout and compile settings. It is treated as derivative/reference material for
now because the local renderer needs deterministic scriptable output from
`model.json`.

### CheckBoxStudio/BUAAThesis

Repository: <https://github.com/CheckBoxStudio/BUAAThesis>

This is reference-only for this project because it targets graduate thesis
rendering. It may still be useful for CJK font setup, bibliography handling, and
general BUAA LaTeX conventions.

## Implemented Spike

New files:

- `buaa_thesis_kit/latex_renderer/__init__.py`
- `buaa_thesis_kit/latex_renderer/renderer.py`
- `scripts/render_latex.py`
- `templates/latex/buaa/main.tex.template`
- `templates/latex/buaa/README.md`
- `templates/latex/buaa/figure/buaamark.pdf`
- `templates/latex/buaa/figure/buaaname.pdf`
- `templates/latex/buaa/bhosc/buaathesis.cls`
- `templates/latex/buaa/bhosc/gbt7714.sty`
- `templates/latex/buaa/bhosc/gbt7714-numerical.bst`
- `templates/latex/buaa/bhosc/gbt7714-author-year.bst`
- `templates/latex/buaa/bhosc/figure/*.pdf`
- `tests/test_latex_renderer.py`

Generated output:

- `output/latex_spike/thesis.tex`
- `output/latex_spike/thesis.pdf`
- `output/latex_spike/report.json`
- `output/latex_spike/data/com_info.tex`
- `output/latex_spike/data/bachelor/bachelor_info.tex`
- `output/latex_spike/data/bachelor/assign.tex`
- `output/latex_spike/data/abstract.tex`
- `output/latex_spike/data/body.tex`
- `output/latex_spike/compare/latex_page_001.png`
- `output/latex_spike/compare/latex_page_003.png`
- `output/latex_spike/compare/latex_page_004.png`
- `output/latex_spike/compare/latex_page_005.png`
- `output/latex_spike/compare/word_page_001.png`
- `output/latex_spike/compare/word_page_005.png`

Command:

```powershell
python scripts/render_latex.py output/pipeline_gate/model.json --out output/latex_spike --degree bachelor --backend bhosc
python scripts/render_latex.py output/pipeline_gate/model.json --out output/latex_spike_master --degree master --backend bhosc
```

Observed compile status:

```json
{
  "status": "success",
  "engine": "xelatex",
  "pdf_exists": true
}
```

## Model Mapping

The renderer maps these fields from `model.json`:

- Metadata: `unit_code`, `student_id`, `classification`, `title_cn`,
  `title_en`, `college`, `major`, `student_name`, `advisor`, `date`
- Front matter: `chinese_abstract`, `keywords_cn`, `english_abstract`,
  `keywords_en`, `acknowledgement`
- Body: `sections`, `tables`, `figures`, `equations`, `references`

Rendered regions:

- Cover
- Declaration
- Chinese abstract
- English abstract when present
- Table of contents
- Body
- Acknowledgement when present
- References when present

Profile behavior:

- `bachelor` writes a BHOSC undergraduate project with `data/bachelor/assign.tex`
  and calls `\maketitle`, so cover, task book, declaration, front matter, and
  page numbering come from `buaathesis.cls`.
- `master` writes a BHOSC graduate project with `data/master/master_info.tex`
  and uses the master title pages. Empty graduate-only fields are represented as
  renderable blanks instead of invented content.
- `lightweight` remains available as `--backend lightweight` for debugging but
  is no longer the recommended fidelity path.

## Missing and Unsupported Content Policy

The renderer intentionally does not guess missing content.

- Missing metadata becomes a blank field on the rendered PDF and a warning in
  `report.json`.
- Missing image assets become clean figure placeholders and `missing_assets`
  report entries.
- Existing but unsupported figures become clean figure placeholders and
  `unsupported_figures` report entries.
- Equations without trusted LaTeX become clean formula placeholders and
  `unsupported_equations` report entries.
- Trusted LaTeX equations are rendered directly.

## Visual Feasibility Notes

The BHOSC-backed undergraduate cover and task book now use the same class and
project structure as the BHOSC sample. With the current `model.json`, several
fields still render blank or as class-provided suffixes because the model is
missing `college`, `major`, `student_name`, `advisor`, English title, English
abstract, references, and task book content.

The current Word PDF comparison still shows unstable cover pagination and
field placement issues. The LaTeX route is therefore more promising for stable
PDF correctness, especially cover/front matter rendering.

The LaTeX route does not solve editable Word output. Keep Word output as a
separate artifact for review, comments, and manual editing while using LaTeX as
a candidate deterministic PDF path.

## Decision

LaTeX is easier for PDF correctness than the current Word OOXML renderer for
fixed BUAA cover/front matter, because layout, page breaks, fonts, counters,
and tables are controlled declaratively and compiled deterministically.

BHOSC/BUAAthesis is the closest reference for both currently supported LaTeX
profiles because it has explicit `bachelor` and `master` modes and published
sample PDFs for each.

Missing before migration:

- Exact task book rendering from model fields.
- Spine rendering requirements.
- Stronger metadata extraction before rendering.
- Figure anchoring from the source document into the section flow.
- Equation conversion from OMML/embedded objects into trusted LaTeX.
- Bibliography normalization into GB/T 7714 or another required style.
- License/attribution decision for retained upstream LaTeX assets.
- Harness gates for LaTeX PDF output, without hiding Word failures.

Recommended architecture:

- Keep Word renderer and its harness failures visible.
- Add LaTeX renderer as a parallel `model.json -> thesis.tex -> thesis.pdf`
  path.
- Compare Word PDF and LaTeX PDF visually in the harness dashboard.
- Promote LaTeX PDF only after it passes independent PDF-specific gates.
