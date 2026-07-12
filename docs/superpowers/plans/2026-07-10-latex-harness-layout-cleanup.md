# BUAA LaTeX Harness Layout Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the本科 LaTeX pipeline use a stable vendored template, render the spine and task book according to the golden reference, reject layout regressions through G28, and safely remove reproducible legacy artifacts.

**Architecture:** Keep extraction and `model.json` unchanged. Move layout-specific validation into a new `layout_validate.py` module, keep BUAAthesis as the page framework, and supply narrowly scoped TeX patches/templates for spine and task-book content. Cleanup is a separate manifest-driven script constrained to the current repository root.

**Tech Stack:** Python 3.11+, pytest, XeLaTeX/BUAAthesis, pypdf, Poppler `pdftoppm`, PowerShell on Windows.

---

### Task 1: Bind the pipeline to the vendored BUAAthesis runtime

**Files:**
- Modify: `buaa_thesis_kit/latex/template_manager.py`
- Modify: `README.md`
- Modify: `docs/LATEX_FEASIBILITY.md`
- Test: `tests/test_buaa_latex_pipeline.py`

- [ ] **Step 1: Write the failing default-template test**

```python
from buaa_thesis_kit.latex.template_manager import resolve_buaa_template


def test_default_buaa_template_is_vendored_and_not_tmp():
    template = resolve_buaa_template()

    assert template.name == "bhosc"
    assert template.as_posix().endswith("templates/latex/buaa/bhosc")
    assert "tmp" not in template.parts
    assert (template / "buaathesis.cls").exists()
```

- [ ] **Step 2: Run the test and verify RED**

Run: `pytest tests/test_buaa_latex_pipeline.py::test_default_buaa_template_is_vendored_and_not_tmp -q`

Expected: FAIL because `resolve_buaa_template()` currently resolves the external junction into `tmp/latex_refs`.

- [ ] **Step 3: Implement the vendored default**

```python
VENDORED_TEMPLATE = ROOT / "templates" / "latex" / "buaa" / "bhosc"
DEFAULT_EXTERNAL_TEMPLATE = ROOT / "templates" / "external" / "BUAAthesis"


def resolve_buaa_template(path: str | Path | None = None) -> Path:
    if path is not None:
        candidate = Path(path).expanduser().resolve(strict=False)
        if not candidate.exists():
            raise FileNotFoundError(f"BUAAthesis template path does not exist: {candidate}")
        return candidate
    if VENDORED_TEMPLATE.exists():
        return VENDORED_TEMPLATE.resolve(strict=False)
    if DEFAULT_EXTERNAL_TEMPLATE.exists():
        return DEFAULT_EXTERNAL_TEMPLATE.resolve(strict=False)
    raise FileNotFoundError("BUAAthesis template runtime is missing from templates/latex/buaa/bhosc")
```

Update examples to omit the external-template argument or use `templates/latex/buaa/bhosc` explicitly.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_buaa_latex_pipeline.py::test_default_buaa_template_is_vendored_and_not_tmp -q`

Expected: PASS.

### Task 2: Preserve task-book dates instead of reusing the cover date

**Files:**
- Modify: `buaa_thesis_kit/latex/render_buaa.py`
- Test: `tests/test_latex_taskbook_references_assets.py`

- [ ] **Step 1: Write failing date-mapping tests**

```python
from buaa_thesis_kit.latex.render_buaa import _com_info


def test_taskbook_date_range_and_blank_defense_date_are_rendered_verbatim():
    model = {
        "metadata": {"date": "2021 年 5 月"},
        "task_book": {
            "date_range": "2020 年 12 月 31 日至 2021 年 5 月 23 日",
            "defense_date": "2021 年 月 日",
        },
        "abstract_cn": {},
        "abstract_en": {},
    }

    tex = _com_info(model, "undergraduate")

    assert r"\thesisbegin{2020}{12}{31}" in tex
    assert r"\thesisend{2021}{5}{23}" in tex
    assert r"\defense{2021}{}{}" in tex
```

- [ ] **Step 2: Run the test and verify RED**

Run: `pytest tests/test_latex_taskbook_references_assets.py::test_taskbook_date_range_and_blank_defense_date_are_rendered_verbatim -q`

Expected: FAIL because all three fields currently use `metadata.date`.

- [ ] **Step 3: Implement strict date parsers and fallback reporting**

Add helpers with these contracts:

```python
def _task_book_date_parts(model: dict[str, Any]) -> tuple[tuple[str, str, str], tuple[str, str, str], tuple[str, str, str], list[str]]:
    task = model.get("task_book") or {}
    values = re.findall(r"(\d{4})\s*年\s*(\d{0,2})\s*月\s*(\d{0,2})\s*日", str(task.get("date_range") or ""))
    fallback_fields: list[str] = []
    if len(values) >= 2:
        begin, end = values[0], values[1]
    else:
        begin = end = _date_parts((model.get("metadata") or {}).get("date", ""))
        fallback_fields.extend(["date_range.begin", "date_range.end"])
    defense_match = re.search(r"(\d{4})\s*年\s*(\d{0,2})\s*月\s*(\d{0,2})\s*日", str(task.get("defense_date") or ""))
    defense = defense_match.groups() if defense_match else ("", "", "")
    return begin, end, defense, fallback_fields
```

Use begin/end/defense in `_com_info()`. Add the fallback list to `_task_book_report()`.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_latex_taskbook_references_assets.py::test_taskbook_date_range_and_blank_defense_date_are_rendered_verbatim -q`

Expected: PASS.

### Task 3: Replace fixed-width task-book fragments with natural TeX paragraphs

**Files:**
- Modify: `buaa_thesis_kit/latex/render_buaa.py`
- Modify: `buaa_thesis_kit/latex/reference_render.py`
- Test: `tests/test_latex_taskbook_references_assets.py`

- [ ] **Step 1: Write failing layout-contract tests**

```python
def test_taskbook_technical_text_is_not_hard_wrapped_in_python():
    text = "第一段短文本。\n第二段包含足够多的中文和 MTF English words so XeLaTeX must choose the line breaks."
    tex = _assign({"task_book": {"raw_materials": text, "work_content": "（1）工作内容"}})

    assert r"\buaaAssignTextParagraph{第一段短文本。}" in tex
    assert r"\buaaAssignTextParagraph{第二段包含足够多的中文和 MTF English words so XeLaTeX must choose the line breaks.}" in tex
    assert "\\buaaAssignTextLine" not in tex


def test_taskbook_reference_style_is_small_four_one_point_five_without_hanging_indent():
    patch = _assign_patch({"metadata": {}, "task_book": {}})

    assert r"\zihao{-4}" in patch
    assert r"\begin{spacing}{1.5}" in patch
    assert r"\hangindent" not in patch
    assert r"\buaaAssignRefParagraph" in patch
```

- [ ] **Step 2: Run both tests and verify RED**

Run: `pytest tests/test_latex_taskbook_references_assets.py -k "not_hard_wrapped or reference_style" -q`

Expected: both FAIL because the renderer emits fixed fragments, `1.12` spacing, and a hanging indent.

- [ ] **Step 3: Render source paragraphs and minimum blank rules**

Implement paragraph extraction without content splitting:

```python
def _assignment_paragraphs(value: Any) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _assignment_text_block_macro(name: str, paragraphs: list[str], minimum_lines: int) -> str:
    estimated = sum(len(_wrap_display_line(item, ASSIGNMENT_TEXT_WIDTH)) for item in paragraphs)
    blanks = max(0, minimum_lines - estimated)
    body = [rf"  \buaaAssignTextParagraph{{{tex_escape(item)}}}" for item in paragraphs]
    body.extend(r"  \buaaAssignBlankLine" for _ in range(blanks))
    return "\n".join([rf"\newcommand{{\{name}}}{{%", *body, "}"])
```

Generate requirements with `minimum_lines=6` and work content with `minimum_lines=7`. Keep legacy fixed-slot macros populated only for BUAAthesis API compatibility; the patched page must use the new paragraph macros.

Define TeX macros in `_assign_patch()`:

```tex
\newcommand{\buaaAssignRuleFill}{\leaders\hrule height 0.4pt depth -0.1pt\hfill\kern0pt}
\newcommand{\buaaAssignTextParagraph}[1]{\par\noindent\uline{#1\hfill}\par}
\newcommand{\buaaAssignBlankLine}{\par\noindent\buaaAssignRuleFill\mbox{}\par}
\newcommand{\buaaAssignRefParagraph}[1]{\par\noindent\uline{#1\hfill}\par}
```

Render both task-book content regions inside `\zihao{-4}` and `spacing{1.5}`. Remove the task-book reference `\hangindent`, `\rightskip=0pt plus 2em`, and trailing `0.55em` paragraph gap. Keep `main_references_tex()` unchanged with `\hangindent=2em`.

- [ ] **Step 4: Verify GREEN and regression coverage**

Run: `pytest tests/test_latex_taskbook_references_assets.py -q`

Expected: all tests pass after updating obsolete fixed-width assertions to assert content preservation and natural-wrap markers.

### Task 4: Add the本科 spine and disable colored final output

**Files:**
- Modify: `buaa_thesis_kit/latex/render_buaa.py`
- Create: generated runtime file `output/<run>/workdir/data/bachelor/spine.tex` through renderer code
- Test: `tests/test_latex_taskbook_references_assets.py`

- [ ] **Step 1: Write failing spine and monochrome tests**

```python
from buaa_thesis_kit.latex.render_buaa import _main_undergraduate, _spine_tex


def test_undergraduate_main_is_monochrome_and_loads_spine_template():
    tex = _main_undergraduate()

    assert "oneside,color," not in tex
    assert r"\include{data/bachelor/spine}" in tex


def test_spine_template_uses_model_title_author_and_school():
    tex = _spine_tex({"metadata": {"title_cn": "基于实拍图像的光电系统性能评估关键技术研究", "student_name": "崔润昊"}})

    assert r"\newcommand{\buaaSpinePage}" in tex
    assert "基\\于\\实\\拍" in tex
    assert "崔\\润\\昊" in tex
    assert "北\\京\\航\\空\\航\\天\\大\\学" in tex
    assert r"\patchcmd{\maketitle}{\titlech}{\titlech\buaaSpinePage}" in tex
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_latex_taskbook_references_assets.py -k "monochrome or spine_template" -q`

Expected: FAIL because the main file contains `color` and no spine runtime exists.

- [ ] **Step 3: Implement the spine runtime**

Write `data/bachelor/spine.tex` from `_write_buaa_project_files()`. `_spine_tex()` escapes each visible character and joins them with `\\[0.18em]`; it defines a full-page, page-number-free three-column layout and patches `\maketitle` immediately after `\titlech`. Keep cover rendering inside BUAAthesis unchanged.

Remove `color` from both undergraduate and master final document-class options, while retaining `AutoFakeBold=true`.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_latex_taskbook_references_assets.py -k "monochrome or spine_template" -q`

Expected: PASS.

### Task 5: Add G28 layout validation and stable failure identity

**Files:**
- Create: `buaa_thesis_kit/latex/layout_validate.py`
- Modify: `buaa_thesis_kit/latex/pipeline.py`
- Create: `tests/test_latex_layout_validate.py`

- [ ] **Step 1: Write failing validator tests**

```python
from buaa_thesis_kit.latex.layout_validate import validate_layout


def test_layout_validator_returns_stable_rich_failures(tmp_path: Path):
    (tmp_path / "thesis.tex").write_text(r"\documentclass[bachelor,color]{buaathesis}", encoding="utf-8")
    result = validate_layout(
        out_dir=tmp_path,
        model={"degree_type": "undergraduate", "task_book": {"date_range": "2020 年 12 月 31 日至 2021 年 5 月 23 日", "references": [{"raw": "[1] A"}]}},
        pdf_pages=["cover", "task book"],
        render_report={"template_used": str(tmp_path / "tmp" / "template")},
    )

    reasons = {item["reason"]: item for item in result["failures"]}
    assert reasons["toc_color_not_black"]["id"] == "H-G28-005"
    assert reasons["frontmatter_spine_missing"]["id"] == "H-G28-004"
    assert set(reasons["toc_color_not_black"]) == {
        "id", "gate", "reason", "region", "evidence_text", "expected", "suggested_fix", "can_fix_now"
    }
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_latex_layout_validate.py -q`

Expected: import failure because `layout_validate.py` does not exist.

- [ ] **Step 3: Implement validator and reports**

Use a constant mapping:

```python
FAILURE_IDS = {
    "template_depends_on_tmp": "H-G28-001",
    "taskbook_technical_layout_contract_invalid": "H-G28-002",
    "taskbook_reference_layout_contract_invalid": "H-G28-003",
    "frontmatter_spine_missing": "H-G28-004",
    "toc_color_not_black": "H-G28-005",
    "taskbook_date_mismatch": "H-G28-006",
    "taskbook_reference_count_mismatch": "H-G28-007",
    "taskbook_page_sequence_invalid": "H-G28-008",
    "taskbook_page_overflow": "H-G28-009",
}
```

`validate_layout()` reads generated TeX contracts and normalized per-page PDF text. It writes `taskbook_layout_report.json` and `frontmatter_sequence_report.json`; when `pdftoppm` is available, render pages 3 and 4 to stable PNG names. Missing Poppler is `needs_review`, not a false pass.

Merge G28 into `_write_latex_gate_reports()` without weakening G20-G27. Convert the existing `add()` helper to emit the same rich fields and assign stable IDs from a gate/reason map.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_latex_layout_validate.py tests/test_latex_taskbook_references_assets.py -q`

Expected: PASS.

### Task 6: Replace name-pattern cleanup with a repository-safe keep manifest

**Files:**
- Modify: `scripts/cleanup_legacy_artifacts.py`
- Modify: `tests/test_cleanup_legacy_artifacts.py`

- [ ] **Step 1: Write failing cleanup-plan tests**

```python
def test_cleanup_plans_generated_tmp_and_non_whitelisted_outputs(tmp_path: Path):
    for path in (
        tmp_path / "generated" / "probe",
        tmp_path / "tmp" / "latex_refs",
        tmp_path / "output" / "latex_spike",
        tmp_path / "output" / "latex_pipeline",
        tmp_path / "output" / "latex_pipeline_pdf",
        tmp_path / "output" / "image",
    ):
        path.mkdir(parents=True)
        (path / "data.bin").write_bytes(b"x" * 16)

    report = plan_cleanup(repo_root=tmp_path)
    removed = {Path(item["path"]).relative_to(tmp_path).as_posix() for item in report["planned"]}

    assert "generated" in removed
    assert "tmp" in removed
    assert "output/latex_spike" in removed
    assert "output/latex_pipeline" not in removed
    assert "output/latex_pipeline_pdf" not in removed
    assert "output/image" not in removed
```

Add a second test that passes an output root outside `repo_root` and expects `ValueError` before deletion.

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_cleanup_legacy_artifacts.py -q`

Expected: FAIL because the current API only scans a limited set of output names.

- [ ] **Step 3: Implement manifest cleanup**

Use explicit constants:

```python
KEEP_OUTPUT = {"latex_pipeline", "latex_pipeline_pdf", "image", "goal_acceptance.md", "goal_acceptance.json", "cleanup_report.json"}


def _assert_within_repo(path: Path, repo_root: Path) -> Path:
    resolved = path.resolve(strict=False)
    root = repo_root.resolve(strict=True)
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"cleanup path escapes repository: {resolved}")
    return resolved
```

Plan `generated` and `tmp` as whole directories plus every non-whitelisted child of `output`. Calculate bytes without following reparse points. `apply_cleanup()` revalidates every path, records before/after free space, and hashes retained PDFs.

- [ ] **Step 4: Verify GREEN and dry run the real repository**

Run: `pytest tests/test_cleanup_legacy_artifacts.py -q`

Expected: PASS.

Run: `python scripts/cleanup_legacy_artifacts.py --repo-root . --dry-run`

Expected: report includes `generated`, `tmp`, and old output children while excluding both latest pipelines and `image`.

### Task 7: End-to-end render, visual review, and cleanup

**Files:**
- Modify: `README.md`
- Update generated artifacts under: `output/latex_pipeline/`, `output/latex_pipeline_pdf/`
- Create: `output/cleanup_report.json`

- [ ] **Step 1: Run focused and full tests**

Run: `pytest tests/test_buaa_latex_pipeline.py tests/test_latex_taskbook_references_assets.py tests/test_latex_layout_validate.py tests/test_cleanup_legacy_artifacts.py -q`

Expected: all focused tests pass.

Run: `pytest tests -q`

Expected: all tests pass with only explicitly deselected integration tests.

- [ ] **Step 2: Run the real DOCX pipeline**

Run:

```powershell
python scripts/run_latex_pipeline.py "C:\Users\admin\Desktop\删减毕设.docx" --buaa-template-path templates\latex\buaa\bhosc --degree-type undergraduate --out output\latex_pipeline --sample-mode truncated
```

Expected: compile success; G20-G26 and G28 pass; G27 may remain `needs_review` only for formula image fallbacks.

- [ ] **Step 3: Run the real PDF pipeline**

Run:

```powershell
python scripts/run_latex_pipeline.py "C:\Users\admin\Desktop\20375284-宋郭睿-毕业论文.pdf" --buaa-template-path templates\latex\buaa\bhosc --degree-type undergraduate --out output\latex_pipeline_pdf --sample-mode truncated
```

Expected: compile success and no new P0/P1 failures.

- [ ] **Step 4: Inspect page evidence**

Open or render these pages from the DOCX output: cover, spine, task-book pages 1-2, declaration, Chinese abstract, English abstract, TOC, body page 1, and first formal-reference page.

Verify:

- task-book technical requirements are small-four, 1.5-spaced, naturally wrapped, and within margins;
- task-book references are small-four, 1.5-spaced, not hanging, and do not split English words;
- formal references remain hanging;
- date range is exact;
- TOC is black;
- all front-matter pages are in the required order.

- [ ] **Step 5: Apply repository-local cleanup**

Run: `python scripts/cleanup_legacy_artifacts.py --repo-root . --apply`

Expected: approximately 1.35 GiB reclaimed; retained PDFs and reports still exist; no path outside the current worktree appears in the removed list.

- [ ] **Step 6: Run post-cleanup verification**

Run: `pytest tests -q`

Run: `python scripts/run_latex_pipeline.py "C:\Users\admin\Desktop\删减毕设.docx" --buaa-template-path templates\latex\buaa\bhosc --degree-type undergraduate --out output\latex_pipeline --sample-mode truncated`

Expected: tests and DOCX pipeline still pass without `tmp/latex_refs` or the external junction.

- [ ] **Step 7: Record final hashes and status**

Update `output/goal_acceptance.md` and `output/goal_acceptance.json` with final PDF hashes, G28 status, cleanup bytes, and the remaining formula-only G27 review items.
