# Citation, Taskbook, and Spine Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a BUAA undergraduate thesis PDF whose numeric citations are superscript cross-references, equation explanation paragraphs are flush left, task-book ruled content reflows within exactly two pages without shrinking fonts, and the spine is a centered framed single-axis layout.

**Architecture:** Keep BHOSC/BUAAthesis immutable and add focused semantic helpers under `buaa_thesis_kit/latex/`. Build citation and paragraph roles in `model.json`, render them through dedicated LaTeX commands, and validate model, TeX, PDF geometry, and page order independently in G28. Task-book pagination is validated by locating its two semantic pages, recompiling after row-count changes, and measuring whether the declaration still begins on the immediately following page.

**Tech Stack:** Python 3.11+, pytest, XeLaTeX/latexmk, BHOSC/BUAAthesis, natbib `\upcite`, PyMuPDF, Poppler, JSON Harness reports.

---

## File Map

- Create `buaa_thesis_kit/latex/citations.py`: deterministic reference keys, citation records, citation-aware text rendering.
- Create `buaa_thesis_kit/latex/body_text.py`: semantic paragraph grouping and equation-explanation roles.
- Create `buaa_thesis_kit/latex/taskbook_lines.py`: fixed-font visual rows and one-rule-per-row task-book TeX.
- Create `buaa_thesis_kit/latex/spine_render.py`: framed, centered, single-axis spine TeX.
- Modify `buaa_thesis_kit/latex/pipeline.py`: add citation records, paragraph roles, and their evidence to the LaTeX model.
- Modify `buaa_thesis_kit/latex/render_buaa.py`: orchestrate the four focused renderers.
- Modify `buaa_thesis_kit/latex/reference_render.py`: emit keyed `\bibitem` entries while retaining formal-reference typography.
- Modify `buaa_thesis_kit/latex/layout_validate.py`: add stable G28 failures and fixed-two-page vertical geometry checks.
- Create `tests/test_latex_citations.py`: citation model and TeX cross-reference tests.
- Create `tests/test_latex_equation_explanations.py`: paragraph-role and no-indent tests.
- Create `tests/test_latex_taskbook_ruled_lines.py`: fixed-font dynamic-row tests.
- Create `tests/test_latex_spine_render.py`: spine structure tests.
- Modify `tests/test_latex_layout_validate.py`: G28 structure and geometry tests.
- Modify `tests/test_latex_taskbook_references_assets.py`: replace superseded natural-`\uline` assertions with the accepted row contract.
- Modify `skills/normalizing-buaa-theses/references/undergraduate-format.md`: document the accepted rules.
- Modify `skills/normalizing-buaa-theses/references/visual-validation.md`: require page-level checks for the changed regions.

### Task 1: Build Deterministic Citation Identity in the Model

**Files:**
- Create: `buaa_thesis_kit/latex/citations.py`
- Modify: `buaa_thesis_kit/latex/pipeline.py:176-225`
- Test: `tests/test_latex_citations.py`

- [ ] **Step 1: Write failing tests for reference keys, ranges, and unresolved targets**

```python
from buaa_thesis_kit.latex.citations import build_citation_records, reference_entries


def test_reference_entries_and_citation_ranges_use_stable_keys():
    references = [
        {"raw": "[1] First reference."},
        {"raw": "[2] Second reference."},
        {"raw": "[3] Third reference."},
        {"raw": "[4] Fourth reference."},
    ]
    body = [{"type": "paragraph", "text": "已有研究[1,2]和后续工作[3-4]。"}]

    entries, reference_issues = reference_entries(references)
    records, citation_issues = build_citation_records(body, entries)

    assert reference_issues == []
    assert [entry["key"] for entry in entries] == ["ref-1", "ref-2", "ref-3", "ref-4"]
    assert records[0]["target_reference_ids"] == ["ref-1", "ref-2"]
    assert records[1]["target_reference_ids"] == ["ref-3", "ref-4"]
    assert citation_issues == []


def test_unresolved_citation_is_reported_without_inventing_reference():
    entries, _ = reference_entries([{"raw": "[1] First reference."}])
    records, issues = build_citation_records(
        [{"type": "paragraph", "text": "无法解析的引用[9]。"}], entries
    )

    assert records[0]["status"] == "needs_review"
    assert records[0]["target_reference_ids"] == []
    assert issues[0]["reason"] == "citation_target_missing"


def test_paragraph_leading_bracket_number_is_not_misclassified_as_citation():
    entries, _ = reference_entries([{"raw": "[1] First reference."}])
    records, issues = build_citation_records(
        [{"type": "paragraph", "text": "[1] 第一项实验步骤"}], entries
    )

    assert records == []
    assert issues == []
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/test_latex_citations.py -q`

Expected: collection fails with `ModuleNotFoundError: buaa_thesis_kit.latex.citations`.

- [ ] **Step 3: Implement citation parsing and stable records**

Create these public functions in `buaa_thesis_kit/latex/citations.py`:

```python
REFERENCE_PREFIX_RE = re.compile(r"^\s*\[(\d+)\]\s*(.*)$", re.DOTALL)
CITATION_RE = re.compile(r"\[(\d+(?:\s*(?:[-–—,，、])\s*\d+)*)\]")


def reference_entries(references: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, item in enumerate(references):
        raw = str(item.get("raw") if isinstance(item, dict) else item).strip()
        match = REFERENCE_PREFIX_RE.match(raw)
        if not match:
            issues.append({"reason": "reference_number_missing", "index": index, "raw": raw})
            continue
        number = int(match.group(1))
        if number in seen:
            issues.append({"reason": "citation_key_duplicate", "number": number, "raw": raw})
            continue
        seen.add(number)
        entries.append({"number": number, "key": f"ref-{number}", "text": match.group(2).strip(), "raw": raw})
    return entries, issues


def expand_citation_numbers(value: str) -> list[int]:
    normalized = re.sub(r"[，、]", ",", value)
    result: list[int] = []
    for part in normalized.split(","):
        token = part.strip()
        range_match = re.fullmatch(r"(\d+)\s*[-–—]\s*(\d+)", token)
        if range_match:
            start, end = map(int, range_match.groups())
            result.extend(range(start, end + 1))
        elif token.isdigit():
            result.append(int(token))
    return list(dict.fromkeys(result))
```

Implement `build_citation_records(body, entries)` by scanning only `paragraph` and text segments inside `paragraph_mixed`, assigning `cite-0001` IDs in source order, and recording `raw_text`, `body_index`, `target_reference_ids`, and `status`.
Treat a bracket number at the start of a semantic paragraph followed by whitespace as list numbering, not a citation.

In `_latex_model_from_thesis_model`, build references before the return value and add:

```python
reference_entries, reference_issues = citations.reference_entries(references)
citation_records, citation_issues = citations.build_citation_records(body, reference_entries)
```

Then expose `citations`, `citation_issues`, and `reference_issues` at the model root and in `debug`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `pytest tests/test_latex_citations.py -q`

Expected: all citation model tests pass.

- [ ] **Step 5: Commit**

```bash
git add buaa_thesis_kit/latex/citations.py buaa_thesis_kit/latex/pipeline.py tests/test_latex_citations.py
git commit -m "feat: model deterministic thesis citations"
```

### Task 2: Render Superscript Cross-References and Keyed Bibliography Entries

**Files:**
- Modify: `buaa_thesis_kit/latex/citations.py`
- Modify: `buaa_thesis_kit/latex/reference_render.py`
- Modify: `buaa_thesis_kit/latex/render_buaa.py:552-625`
- Modify: `tests/test_latex_citations.py`
- Modify: `tests/test_latex_taskbook_references_assets.py:491-504`

- [ ] **Step 1: Add failing TeX contract tests**

```python
from buaa_thesis_kit.latex.citations import reference_entries, render_text_with_citations
from buaa_thesis_kit.latex.reference_render import main_references_tex


def test_body_citations_render_as_upcite_and_bibliography_has_matching_keys():
    references = [{"raw": "[1] First."}, {"raw": "[2] Second."}]
    entries, _ = reference_entries(references)

    body_tex, unresolved = render_text_with_citations("结论见文献[1-2]。", entries)
    reference_tex = main_references_tex(references)

    assert body_tex == r"结论见文献\upcite{ref-1,ref-2}。"
    assert unresolved == []
    assert r"\bibitem{ref-1} First." in reference_tex
    assert r"\bibitem{ref-2} Second." in reference_tex
    assert r"\begin{thebibliography}{99}" in reference_tex


def test_missing_target_remains_visible_and_is_not_fake_cross_reference():
    entries, _ = reference_entries([{"raw": "[1] First."}])
    tex, unresolved = render_text_with_citations("缺失[9]。", entries)

    assert tex == r"缺失[9]。"
    assert unresolved == [9]
    assert "ref-9" not in tex
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `pytest tests/test_latex_citations.py -q`

Expected: fails because `render_text_with_citations` and keyed `\bibitem` output do not exist.

- [ ] **Step 3: Implement citation-aware escaping and bibliography output**

Add `render_text_with_citations` to `citations.py`. Escape every non-citation span with `tex_escape`; emit `\upcite{...}` only when all referenced numbers resolve; otherwise preserve the escaped original marker and return unresolved numbers.

Replace `main_references_tex` with a natbib-compatible environment:

```python
def main_references_tex(references: list[Any]) -> str:
    entries, _issues = citations.reference_entries(references)
    if not entries:
        return '% !Mode:: "TeX:UTF-8"\n\\cleardoublepage\n'
    lines = [
        '% !Mode:: "TeX:UTF-8"',
        r"\cleardoublepage",
        r"\phantomsection",
        r"\addcontentsline{toc}{chapter}{参考文献}",
        r"\begingroup\zihao{-4}\begin{spacing}{1.5}",
        r"\begin{thebibliography}{99}",
    ]
    lines.extend(rf"\bibitem{{{entry['key']}}} {tex_escape(entry['text'])}" for entry in entries)
    lines.extend([r"\end{thebibliography}", r"\end{spacing}\endgroup", r"\cleardoublepage"])
    return "\n".join(lines) + "\n"
```

In `_body(model)`, build entries once and route every normal body paragraph and every text segment in `paragraph_mixed` through `render_text_with_citations`. Do not apply citation conversion to abstracts, task-book text, equations, captions, acknowledgements, or the bibliography itself.

Add citation counts and unresolved markers to the renderer report.

- [ ] **Step 4: Replace the superseded formal-reference test**

Change `test_final_references_use_hanging_indent_not_plain_noindent_paragraphs` to assert `thebibliography`, `\bibitem{ref-1}`, small-four size, and 1.5 spacing. The list environment supplies hanging labels; the test must no longer require the old unkeyed `\buaaMainReferenceEntry` macro.

- [ ] **Step 5: Run focused renderer tests**

Run: `pytest tests/test_latex_citations.py tests/test_latex_taskbook_references_assets.py -q`

Expected: all tests pass and no body test expects a baseline `[n]` marker.

- [ ] **Step 6: Commit**

```bash
git add buaa_thesis_kit/latex/citations.py buaa_thesis_kit/latex/reference_render.py buaa_thesis_kit/latex/render_buaa.py tests/test_latex_citations.py tests/test_latex_taskbook_references_assets.py
git commit -m "feat: render superscript citation cross-references"
```

### Task 3: Model and Render Flush-Left Equation Explanations

**Files:**
- Create: `buaa_thesis_kit/latex/body_text.py`
- Modify: `buaa_thesis_kit/latex/pipeline.py:176-225,259-325`
- Modify: `buaa_thesis_kit/latex/render_buaa.py:552-580,1024-1064`
- Test: `tests/test_latex_equation_explanations.py`

- [ ] **Step 1: Write failing role and rendering tests**

```python
from buaa_thesis_kit.latex.body_text import annotate_body_paragraphs
from buaa_thesis_kit.latex.render_buaa import _body


def test_equation_explanation_role_is_assigned_per_semantic_paragraph():
    body = [{"type": "paragraph", "text": "式中，x 为输入。\n普通正文仍需缩进。"}]
    annotated = annotate_body_paragraphs(body, source_type="docx")

    assert annotated[0]["paragraphs"] == [
        {"text": "式中，x 为输入。", "role": "equation_explanation"},
        {"text": "普通正文仍需缩进。", "role": "body"},
    ]


def test_equation_explanation_uses_noindent_and_non_orphan_marker():
    tex = _body(
        {
            "references": [],
            "body": [
                {
                    "type": "paragraph",
                    "paragraphs": [{"text": "式中，x 为输入。", "role": "equation_explanation"}],
                }
            ],
        }
    )

    assert r"\newcommand{\buaaEquationExplanation}[1]{\par\noindent #1\par}" in tex
    assert r"\buaaEquationExplanation{\mbox{式中，}\nobreak{}x 为输入。}" in tex
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_latex_equation_explanations.py -q`

Expected: import fails because `body_text.py` does not exist.

- [ ] **Step 3: Implement semantic paragraphs and roles**

Create `body_text.py` with:

```python
EXPLANATION_RE = re.compile(r"^(上式中|式中|其中|这里)([，,:：]?)(.*)$", re.DOTALL)


def paragraph_role(text: str) -> str:
    return "equation_explanation" if EXPLANATION_RE.match(text.lstrip()) else "body"


def semantic_paragraphs(value: Any, source_type: str) -> list[str]:
    if source_type == "pdf":
        return reflow_pdf_paragraphs(value)
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def annotate_body_paragraphs(body: list[dict[str, Any]], source_type: str) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for item in body:
        current = dict(item)
        if current.get("type") == "paragraph":
            current["paragraphs"] = [
                {"text": text, "role": paragraph_role(text)}
                for text in semantic_paragraphs(current.get("text"), source_type)
            ]
        annotated.append(current)
    return annotated
```

Move the existing PDF physical-line reflow logic from `render_buaa.py` into `body_text.py`, retaining a compatibility wrapper in `render_buaa.py` for existing tests.

Call `annotate_body_paragraphs` before citation-record construction in `pipeline.py`.

- [ ] **Step 4: Implement the dedicated LaTeX paragraph command**

Define `\buaaEquationExplanation` once at the beginning of `body.tex`. Split the marker with `EXPLANATION_RE`, render `\mbox{marker+punctuation}\nobreak{}` followed by citation-aware escaped content, and render ordinary paragraphs through the unchanged body paragraph path.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_latex_equation_explanations.py tests/test_latex_taskbook_references_assets.py -q`

Expected: explanation tests pass and PDF line-reflow regressions remain green.

- [ ] **Step 6: Commit**

```bash
git add buaa_thesis_kit/latex/body_text.py buaa_thesis_kit/latex/pipeline.py buaa_thesis_kit/latex/render_buaa.py tests/test_latex_equation_explanations.py tests/test_latex_taskbook_references_assets.py
git commit -m "feat: render equation explanations flush left"
```

### Task 4: Replace Task-Book Rule Joins with Dynamic Official Rows

**Files:**
- Create: `buaa_thesis_kit/latex/taskbook_lines.py`
- Modify: `buaa_thesis_kit/latex/render_buaa.py:358-432,900-1017`
- Modify: `buaa_thesis_kit/latex/reference_render.py`
- Create: `tests/test_latex_taskbook_ruled_lines.py`
- Modify: `tests/test_latex_taskbook_references_assets.py:71-168,387-429,507-542`

- [ ] **Step 1: Write failing one-rule-per-row tests**

```python
from buaa_thesis_kit.latex.render_buaa import _assign, _assign_patch


def test_taskbook_rows_use_one_official_ulinel_without_joined_rules():
    model = {
        "task_book": {
            "raw_materials": "第一段技术要求。第二句继续说明并自然增加横线行数。",
            "work_content": "（1）第一项工作\n（2）第二项工作",
            "references": [{"raw": "[1] A long reference that wraps onto a continuation row."}],
        }
    }
    assign = _assign(model)
    patch = _assign_patch({"metadata": {}, "task_book": {}})

    assert r"\buaaAssignRuledLine" in assign
    assert r"\newcommand{\buaaAssignRuledLine}[1]{\par\noindent\ulinel{#1}\par}" in patch
    assert r"\leaders\hrule" not in patch
    assert r"\allowbreak{}" not in assign
    assert r"\zihao{-4}" in assign


def test_more_content_adds_rows_without_font_reduction_or_truncation():
    short = _assign({"task_book": {"raw_materials": "短文本。"}})
    long_text = "技术要求内容。" * 80
    long = _assign({"task_book": {"raw_materials": long_text}})

    assert long.count(r"\buaaAssignRuledLine") > short.count(r"\buaaAssignRuledLine")
    assert "技术要求内容" in long
    assert "scriptsize" not in long and "resizebox" not in long


def test_taskbook_reference_continuation_has_hanging_indent():
    assign = _assign(
        {"task_book": {"references": [{"raw": "[1] " + "Reference words " * 20}]}}
    )
    assert r"\buaaAssignRuledLine{\hspace*{2em}" in assign
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_latex_taskbook_ruled_lines.py -q`

Expected: fails because the current renderer emits paragraph `\uline` plus `\leaders\hrule` and `\allowbreak`.

- [ ] **Step 3: Implement deterministic visual rows at fixed small-four size**

Create `taskbook_lines.py` with these public functions:

```python
def text_rows(value: Any, *, width: int, minimum_rows: int, source_type: str) -> list[dict[str, Any]]:
    rows = [
        {"text": line, "indent_em": 0}
        for paragraph in body_text.semantic_paragraphs(value, source_type)
        for line in wrap_display_line(paragraph, width)
    ]
    rows.extend({"text": "", "indent_em": 0} for _ in range(max(0, minimum_rows - len(rows))))
    return rows


def reference_rows(references: list[Any], *, width: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in references:
        raw = str(item.get("raw") if isinstance(item, dict) else item).strip()
        wrapped = wrap_display_line(raw, width)
        rows.extend(
            {"text": line, "indent_em": 0 if index == 0 else 2}
            for index, line in enumerate(wrapped)
        )
    return rows


def ruled_block_macro(name: str, rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        prefix = r"\hspace*{2em}" if row["indent_em"] else ""
        body.append(rf"  \buaaAssignRuledLine{{{prefix}{tex_escape(row['text'])}}}")
    return "\n".join([rf"\newcommand{{\{name}}}{{%", r"  \begingroup\zihao{-4}\begin{spacing}{1.5}%", *body, r"  \end{spacing}\endgroup%", "}"])
```

Move the existing display-width helpers into this module. Keep compatibility wrappers only where tests or callers still import the old private names.

- [ ] **Step 4: Patch only the official row slots**

In `_assign`, generate requirement rows, work rows, and reference rows. In `_assign_patch`, define only `\buaaAssignRuledLine` and replace the official five, six, and eight `\ulinel` slot sequences with the generated blocks. Remove `\buaaAssignRuleFill`, `\buaaAssignTextParagraph`, `\buaaAssignRefParagraph`, and character-by-character break insertion.

- [ ] **Step 5: Replace superseded tests after RED is established**

Update tests that require natural TeX paragraph wrapping or `\allowbreak`. New assertions must require dynamic row count, retained tail text, `\zihao{-4}`, a single `\ulinel` mechanism per row, and no font reduction.

- [ ] **Step 6: Run task-book tests**

Run: `pytest tests/test_latex_taskbook_ruled_lines.py tests/test_latex_taskbook_references_assets.py -q`

Expected: all task-book tests pass.

- [ ] **Step 7: Commit**

```bash
git add buaa_thesis_kit/latex/taskbook_lines.py buaa_thesis_kit/latex/render_buaa.py buaa_thesis_kit/latex/reference_render.py tests/test_latex_taskbook_ruled_lines.py tests/test_latex_taskbook_references_assets.py
git commit -m "fix: reflow taskbook content on continuous ruled rows"
```

### Task 5: Render the Framed Single-Axis Spine

**Files:**
- Create: `buaa_thesis_kit/latex/spine_render.py`
- Modify: `buaa_thesis_kit/latex/render_buaa.py:9-13,298-337`
- Create: `tests/test_latex_spine_render.py`
- Modify: `tests/test_latex_taskbook_references_assets.py:171-190`

- [ ] **Step 1: Write a failing structure test**

```python
from buaa_thesis_kit.latex.spine_render import spine_tex


def test_spine_is_one_centered_frame_and_one_vertical_axis():
    tex = spine_tex(
        {"title_cn": "基于实拍图像的光电系统性能评估关键技术研究", "student_name": "崔润昊"}
    )

    assert tex.count(r"\fbox{") == 1
    assert tex.count(r"\begin{minipage}") == 1
    assert r"\makebox[\textwidth][c]" in tex
    assert r"\hfill" not in tex
    assert tex.index(r"基\\于\\实\\拍") < tex.index(r"崔\\润\\昊")
    assert tex.index(r"崔\\润\\昊") < tex.index(r"北\\京\\航\\空\\航\\天\\大\\学")
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_latex_spine_render.py -q`

Expected: import fails because `spine_render.py` does not exist.

- [ ] **Step 3: Implement the centered frame**

Implement `vertical_text` and `spine_tex` in the new module. The generated page must use one `\makebox[\textwidth][c]`, one `\fbox`, one fixed-height minipage, and three `\shortstack` blocks separated vertically inside the same minipage. Use `\fboxrule=0.4pt`, `\fboxsep=0pt`, frame width `3.4em`, and frame height `0.78\textheight`. Preserve the existing `\patchcmd{\maketitle}` insertion point.

Replace `_spine_tex` in `render_buaa.py` with a delegation to `spine_render.spine_tex(_metadata(model))`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_latex_spine_render.py tests/test_latex_taskbook_references_assets.py -q`

Expected: all spine tests pass and the old three-minipage assertion is gone.

- [ ] **Step 5: Commit**

```bash
git add buaa_thesis_kit/latex/spine_render.py buaa_thesis_kit/latex/render_buaa.py tests/test_latex_spine_render.py tests/test_latex_taskbook_references_assets.py
git commit -m "fix: render framed single-axis thesis spine"
```

### Task 6: Add Independent G28 Structural and Geometry Gates

**Files:**
- Modify: `buaa_thesis_kit/latex/layout_validate.py`
- Modify: `tests/test_latex_layout_validate.py`

- [ ] **Step 1: Extend fixture files and write failing gate tests**

Extend `_write_contract_files` to create `data/body.tex` containing `\upcite{ref-1}` and `\buaaEquationExplanation`, keyed `reference.tex`, a one-rule task-book patch, and framed spine TeX.

Add tests that assert these exact IDs:

```python
EXPECTED_IDS = {
    "citation_not_superscript_crossref": "H-G28-011",
    "citation_target_missing": "H-G28-012",
    "citation_key_duplicate": "H-G28-013",
    "equation_explanation_indented": "H-G28-014",
    "equation_explanation_marker_orphan": "H-G28-015",
    "taskbook_rule_join_visible": "H-G28-016",
    "taskbook_font_size_reduced": "H-G28-017",
    "spine_frame_missing": "H-G28-018",
    "spine_axis_misaligned": "H-G28-019",
    "spine_not_page_centered": "H-G28-020",
}


def test_layout_validator_rejects_raw_citation_and_missing_target(tmp_path):
    _write_contract_files(tmp_path)
    body = tmp_path / "workdir" / "data" / "body.tex"
    body.write_text("正文引用[9]。\n", encoding="utf-8")
    result = validate_layout(
        tmp_path,
        _model(),
        {"template_used": str(tmp_path / "templates" / "latex" / "buaa" / "bhosc")},
        pdf_pages=_good_pages(),
        text_bounds={3: [], 4: []},
        spine_geometry={"page_width": 595.28, "frame": [280.0, 80.0, 315.28, 740.0], "text_centers": [297.64]},
        render_evidence=False,
    )
    reasons = {item["reason"]: item["id"] for item in result["failures"]}
    assert reasons["citation_not_superscript_crossref"] == "H-G28-011"
    assert reasons["citation_target_missing"] == "H-G28-012"
```

Add a fixed-two-page test with task-book blocks shifted down but inside the page and a failure case with `y1 > page_height - 55`.

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_latex_layout_validate.py -q`

Expected: fails because the new failure IDs, `spine_geometry` input, and vertical bounds do not exist.

- [ ] **Step 3: Implement semantic page location and vertical measurement**

Read `body.tex` in addition to existing artifacts. Locate task-book page 1 by its title, task-book page 2 by “主要参考资料”, and verify they are contiguous. Add `y0`, `y1`, and `page_height` to `_pdf_text_bounds`; inspect the located pages rather than assuming page numbers before detection.

After dynamic rows move later fields, pass only when:

```python
taskbook_pages == [title_page, title_page + 1]
and declaration_page == title_page + 2
and all(block["y1"] <= block["page_height"] - 55.0 for block in taskbook_blocks)
```

Do not fail merely because rows increased or later blocks moved down within those bounds.

- [ ] **Step 4: Implement citation, explanation, and task-book TeX gates**

Parse `\upcite{}` keys from `body.tex` and `\bibitem{}` keys from `reference.tex`. Fail on resolvable raw numeric citations, missing targets, or duplicate keys. Require the dedicated explanation macro for every model paragraph role and reject a PDF text line containing only an explanation marker. Reject `\leaders\hrule`, `\buaaAssignRuleFill`, character-level `\allowbreak`, `scriptsize`, or `resizebox` in task-book artifacts.

- [ ] **Step 5: Implement spine vector geometry extraction**

Add optional `spine_geometry` to `validate_layout`; when absent, use PyMuPDF page 2 drawings to find one tall narrow rectangle and text-block centers. Pass only when the frame center differs from `page_width / 2` by at most 3 pt and all title/name/school centers differ from the frame center by at most 3 pt.

- [ ] **Step 6: Run G28 tests**

Run: `pytest tests/test_latex_layout_validate.py -q`

Expected: all G28 tests pass with stable rich failure objects.

- [ ] **Step 7: Commit**

```bash
git add buaa_thesis_kit/latex/layout_validate.py tests/test_latex_layout_validate.py
git commit -m "test: gate citation taskbook and spine geometry"
```

### Task 7: Update the Agent Skill Contract

**Files:**
- Modify: `skills/normalizing-buaa-theses/references/undergraduate-format.md`
- Modify: `skills/normalizing-buaa-theses/references/visual-validation.md`
- Modify: `tests/test_buaa_thesis_skill_contract.py`

- [ ] **Step 1: Write failing contract assertions**

Add assertions that the Skill documentation contains these explicit terms:

```python
for required in (
    "\\upcite",
    "\\bibitem",
    "公式说明段顶格",
    "任务书固定为连续两页",
    "增加横线后重新编译",
    "不得缩小字号",
    "窄框单轴书脊",
):
    assert required in combined_skill_text
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_buaa_thesis_skill_contract.py -q`

Expected: fails on the new terms.

- [ ] **Step 3: Document the execution and review rules**

Document the exact model-to-TeX citation mapping, explanation roles, two-page compile-measure loop, one-`\ulinel` row contract, and spine frame checks. State that Agent visual review supplements but cannot override G28 failures.

- [ ] **Step 4: Run and verify GREEN**

Run: `pytest tests/test_buaa_thesis_skill_contract.py -q`

Expected: passes.

- [ ] **Step 5: Commit**

```bash
git add skills/normalizing-buaa-theses/references/undergraduate-format.md skills/normalizing-buaa-theses/references/visual-validation.md tests/test_buaa_thesis_skill_contract.py
git commit -m "docs: codify thesis citation and taskbook review"
```

### Task 8: Run the Real DOCX Red-Green Acceptance Cycle

**Files:**
- Runtime output only: `.verify-refinements/`
- Final delivery: `output/`

- [ ] **Step 1: Run focused regression suites**

```powershell
pytest tests/test_latex_citations.py `
  tests/test_latex_equation_explanations.py `
  tests/test_latex_taskbook_ruled_lines.py `
  tests/test_latex_spine_render.py `
  tests/test_latex_layout_validate.py `
  tests/test_latex_taskbook_references_assets.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the complete suite**

Run: `pytest tests -q`

Expected: no failures; existing environment-dependent skips remain documented.

- [ ] **Step 3: Run the real source through extraction and rendering**

```powershell
python scripts/run_latex_pipeline.py `
  "C:\Users\admin\Desktop\删减毕设.docx" `
  --buaa-template-path templates/latex/buaa/bhosc `
  --degree-type undergraduate `
  --out .verify-refinements/initial `
  --sample-mode truncated
```

Expected: extraction and compilation complete; any equation review items remain explicit rather than auto-approved.

- [ ] **Step 4: Apply the hash-bound equation review ledger**

Inspect each candidate/source-preview pair. For the unchanged source SHA `e70eaea3a0196e6f586335568a7619bbbb30669e7481fcb85f995615bb63bbdd`, retain the previously verified corrections only when the newly generated source previews match:

```text
eq-13: OTF\left( {\xi ,\eta } \right)=MTF\left( {\xi ,\eta } \right)e^{i\cdot PhTF\left( {\xi ,\eta } \right)}
eq-14: MTF\left( {\xi ,\eta } \right)=\left| {OTF\left( {\xi ,\eta } \right)} \right|,\quad PhTF\left( {\xi ,\eta } \right)=\arg \left( {OTF\left( {\xi ,\eta } \right)} \right)
eq-28: \xi={f_{sp}},\quad \eta=0
eq-31: OTF\left( {{f_{sp}}} \right)=MTF\left( {{f_{sp}}} \right)e^{i\cdot PhTF\left( {{f_{sp}}} \right)}
```

Write `.verify-refinements/equation_review.json` with the exact source path/SHA and each new candidate/source-preview/rendered SHA, then rerun with `--equation-review .verify-refinements/equation_review.json` into `.verify-refinements/reviewed`.

Expected: all equation items pass and G20-G28 are evaluated against the reviewed candidate.

- [ ] **Step 5: Verify fixed-two-page task-book geometry from the compiled PDF**

Confirm by extracted markers and PyMuPDF bounds:

- Task-book title page and “主要参考资料” page are contiguous.
- Declaration begins on the immediately following page.
- Added rows move later blocks down but every task-book block remains above `page_height - 55 pt`.
- Technical requirements and references remain `\zihao{-4}`.
- No `\leaders\hrule` or character-level `\allowbreak` remains.

Expected: G28 passes; row growth alone is not reported as overflow.

- [ ] **Step 6: Perform Agent visual review of the exact PDF SHA**

Render every PDF page to `page_NNN_<region>.png`. On changed pages, inspect at original resolution:

- Spine: one closed frame, one centered axis, title/name/school in order.
- Task-book pages: continuous rules, no seams, no clipping, no third task-book page.
- Citation pages: numeric citations are visibly superscript.
- Formula pages: “式中/其中/这里/上式中” starts at the left boundary and is not orphaned.

Create `visual_review.json` beside the screenshots with the exact PDF SHA, page count, page bbox, screenshot name, status, checks, and failure IDs. Every screenshot must pixel-bind to the declared PDF page.

- [ ] **Step 7: Package the reviewed delivery**

```powershell
python scripts/package_agent_delivery.py `
  "C:\Users\admin\Desktop\删减毕设.docx" `
  --run .verify-refinements/reviewed `
  --output output `
  --visual-manifest .verify-refinements/reviewed/visual/visual_review.json `
  --template templates/latex/buaa/bhosc `
  --replace `
  --out .verify-refinements/package_report.json
```

Expected: `package_status=packaged`, source identity matches, flattened TeX recompiles to a pixel-identical PDF, and `output/` contains only `thesis.docx`, `thesis.pdf`, `thesis.tex`, `model.json`, `report.md`, `failure_queue.json`, and `image/`.

- [ ] **Step 8: Run final validators and clean temporary evidence**

Run both final delivery profiles against `output/`. Verify `failure_queue.json` is empty and all page reviews pass. Resolve `.verify-refinements` to an absolute path, prove it is inside this worktree, then remove it recursively. Do not remove or alter any path outside the worktree.

- [ ] **Step 9: Commit and push the completed implementation**

```bash
git status --short
git diff --check -- . ":(exclude)templates/latex/buaa/**/*.pdf"
git add buaa_thesis_kit tests skills docs
git commit -m "feat: refine BUAA citation taskbook and spine layout"
git push origin feature/native-latex-equations
```

Expected: working tree clean, remote branch updated, and PR #1 contains the implementation commits.
