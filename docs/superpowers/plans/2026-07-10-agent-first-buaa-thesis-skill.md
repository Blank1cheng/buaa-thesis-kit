# Agent-first BUAA Thesis Normalization Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a portable Agent Skill that normalizes complete BUAA theses from DOCX/PDF evidence, renders with BUAAthesis, and uses Harness profiles as an independent acceptance judge.

**Architecture:** `skills/normalizing-buaa-theses/SKILL.md` is the only workflow entry point. Focused references contain extraction, rendering, formula, visual-review, and output rules. Existing extractors, XeLaTeX renderers, OCR adapters, and validators remain optional tools selected by the Agent. A small Harness profile module maps existing gate reports to `latex_pdf`, `word_editable`, `agent_visual_review`, and `legacy_word_layout` without changing gate outcomes.

**Tech Stack:** Agent Skills Markdown/YAML, Python 3.11+, pytest, PyYAML, existing BUAAthesis XeLaTeX renderer and Harness JSON reports.

---

## File Map

- `skills/normalizing-buaa-theses/SKILL.md`: concise Agent execution contract and decision flow.
- `skills/normalizing-buaa-theses/agents/openai.yaml`: discoverability metadata.
- `skills/normalizing-buaa-theses/references/*.md`: detailed rules loaded only when needed.
- `skills/normalizing-buaa-theses/evals/*.md`: reusable baseline and post-Skill scenarios.
- `buaa_thesis_kit/harness/profiles.py`: profile loading and gate-board evaluation.
- `buaa_thesis_kit/harness/config/profiles.yaml`: required and excluded gates per output path.
- `scripts/validate_agent_delivery.py`: thin CLI that validates a finished output bundle and visual-review manifest.
- `tests/test_buaa_thesis_skill_contract.py`: static and behavioral Skill contract tests.
- `tests/test_harness_profiles.py`: profile and delivery-Harness tests.
- `docs/AGENT_SKILL_WORKFLOW.md`: repository-facing usage and migration notes.

### Task 1: Capture Baseline Agent Failures

**Files:**
- Create: `skills/normalizing-buaa-theses/evals/prompts/docx-source-priority.md`
- Create: `skills/normalizing-buaa-theses/evals/prompts/pdf-visual-formula.md`
- Create: `skills/normalizing-buaa-theses/evals/prompts/harness-authority.md`
- Create: `skills/normalizing-buaa-theses/evals/docx-source-priority.md`
- Create: `skills/normalizing-buaa-theses/evals/pdf-visual-formula.md`
- Create: `skills/normalizing-buaa-theses/evals/harness-authority.md`
- Create: `tests/skill_evals/baseline.json`

- [ ] **Step 1: Write three raw prompts and three grader rubrics**

Each `evals/prompts/*.md` file must contain only the raw scenario shown to the Agent. Each matching `evals/*.md` rubric must contain `Prompt`, `Expected decisions`, and `Forbidden decisions`, and is available only to the grader. The scenarios must independently test:

```text
DOCX: a PDF conversion disagrees with w:t/table/textbox values; DOCX XML must win.
PDF formula: image recognition gives a compilable but ambiguous subscript; it must remain needs_review.
Harness: the Agent visually likes the PDF but G23/G28 failed; it must not claim pass.
```

- [ ] **Step 2: Run the prompts with a clean Agent that is not given the new Skill**

Record the exact answer, scenario type, prompt and rubric paths, whether each required decision was made, and observed rationalizations in `tests/skill_evals/baseline.json`. Derive pass/fail counts from the scenario results rather than hard-coding a 2/1 split, and require at least one discriminator to fail before Skill implementation; otherwise strengthen the scenario rather than weakening expected behavior. Positive controls may remain green when they demonstrate behavior the Skill must preserve.

- [ ] **Step 3: Verify the baseline is genuinely red**

Run:

```powershell
python -c "import json; p=json.load(open('tests/skill_evals/baseline.json',encoding='utf-8')); assert any(not x['passed'] for x in p['scenarios'])"
```

Expected: exit code `0`, proving at least one unassisted Agent failure.

- [ ] **Step 4: Commit the baseline fixtures**

```powershell
git add skills/normalizing-buaa-theses/evals/prompts skills/normalizing-buaa-theses/evals/*.md tests/skill_evals/baseline.json
git commit -m "test: capture thesis skill agent baselines"
```

### Task 2: Add a Failing Skill Contract Test

**Files:**
- Create: `tests/test_buaa_thesis_skill_contract.py`

- [ ] **Step 1: Write the failing contract tests**

```python
from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "normalizing-buaa-theses"


def test_skill_has_portable_agent_skill_structure():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---", 2)[1])
    assert frontmatter["name"] == "normalizing-buaa-theses"
    assert frontmatter["description"].startswith("Use when")
    assert (SKILL / "agents" / "openai.yaml").is_file()


def test_skill_is_agent_first_and_keeps_harness_authoritative():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for token in (
        "DOCX XML",
        "Agent visual",
        "Harness",
        "failure_queue.json",
        "Do not claim pass",
    ):
        assert token in text
    assert "setup_equation_ocr.py" not in text


def test_skill_references_exist_and_output_contract_is_flat():
    required = {
        "source-extraction.md",
        "thesis-model.md",
        "undergraduate-format.md",
        "graduate-format.md",
        "latex-rendering.md",
        "equation-handling.md",
        "visual-validation.md",
        "failure-taxonomy.md",
        "output-contract.md",
    }
    assert required <= {p.name for p in (SKILL / "references").glob("*.md")}
    output = (SKILL / "references" / "output-contract.md").read_text(encoding="utf-8")
    for token in ("output/thesis.docx", "output/thesis.pdf", "output/thesis.tex", "output/image/"):
        assert token in output
```

- [ ] **Step 2: Run the test and verify it fails because the Skill is absent**

Run: `pytest tests/test_buaa_thesis_skill_contract.py -q`

Expected: FAIL with `FileNotFoundError` for `skills/normalizing-buaa-theses/SKILL.md`.

- [ ] **Step 3: Commit the red contract test**

```powershell
git add tests/test_buaa_thesis_skill_contract.py
git commit -m "test: define agent-first thesis skill contract"
```

### Task 3: Implement the Minimal Agent-first Skill

**Files:**
- Create: `skills/normalizing-buaa-theses/SKILL.md`
- Create: `skills/normalizing-buaa-theses/agents/openai.yaml`
- Create: `skills/normalizing-buaa-theses/references/source-extraction.md`
- Create: `skills/normalizing-buaa-theses/references/thesis-model.md`
- Create: `skills/normalizing-buaa-theses/references/undergraduate-format.md`
- Create: `skills/normalizing-buaa-theses/references/graduate-format.md`
- Create: `skills/normalizing-buaa-theses/references/latex-rendering.md`
- Create: `skills/normalizing-buaa-theses/references/equation-handling.md`
- Create: `skills/normalizing-buaa-theses/references/visual-validation.md`
- Create: `skills/normalizing-buaa-theses/references/failure-taxonomy.md`
- Create: `skills/normalizing-buaa-theses/references/output-contract.md`

- [ ] **Step 1: Write concise Skill frontmatter and execution loop**

Use this frontmatter and keep the main body below 500 words:

```yaml
---
name: normalizing-buaa-theses
description: Use when an Agent must turn a BUAA undergraduate or graduate DOCX/PDF thesis into an auditable, template-correct LaTeX/PDF delivery while preserving editable content and validating layout, figures, equations, references, and front matter.
---
```

The body must require capability detection, DOCX XML priority, evidence-backed model creation, BUAAthesis rendering, Agent visual review, Harness evaluation, one-failure repair loops, and final output cleanup. It must explicitly say `Do not claim pass` when any required Harness gate or visual review item is unresolved.

- [ ] **Step 2: Write focused references**

Each reference must provide direct procedures and acceptance checks rather than prose history. `equation-handling.md` must establish:

```text
OMML/MTEF > verified text > Agent visual transcription > optional external OCR
```

It must require crop evidence, native LaTeX, standalone compilation, symbol-by-symbol visual checking, and `needs_review` for ambiguity. External OCR must not be required.

- [ ] **Step 3: Add Agent UI metadata**

```yaml
interface:
  display_name: "Normalize BUAA Thesis"
  short_description: "Normalize BUAA DOCX/PDF theses with auditable PDF validation"
```

- [ ] **Step 4: Validate Skill structure and contract**

Run:

```powershell
python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\normalizing-buaa-theses
pytest tests/test_buaa_thesis_skill_contract.py -q
```

Expected: Skill validation succeeds and all contract tests pass.

- [ ] **Step 5: Commit the Skill**

```powershell
git add skills/normalizing-buaa-theses tests/test_buaa_thesis_skill_contract.py
git commit -m "feat: add agent-first BUAA thesis normalization skill"
```

### Task 4: Add Harness Profiles Without Loosening Gates

**Files:**
- Create: `buaa_thesis_kit/harness/profiles.py`
- Create: `buaa_thesis_kit/harness/config/profiles.yaml`
- Create: `tests/test_harness_profiles.py`

- [ ] **Step 1: Write failing profile tests**

```python
from buaa_thesis_kit.harness.profiles import evaluate_profile, load_profile


def test_latex_profile_requires_pdf_render_and_layout_gates():
    profile = load_profile("latex_pdf")
    assert {"G20", "G23", "G24", "G27", "G28"} <= set(profile.required_gates)
    assert "G07" not in profile.required_gates


def test_failed_required_gate_cannot_be_hidden_by_other_passes():
    result = evaluate_profile(
        "latex_pdf",
        {
            "G20": {"status": "pass"},
            "G23": {"status": "failed"},
            "G24": {"status": "pass"},
            "G27": {"status": "pass"},
            "G28": {"status": "pass"},
        },
    )
    assert result["status"] == "failed"
    assert result["failed_gates"] == ["G23"]


def test_visual_profile_requires_review_manifest():
    result = evaluate_profile("agent_visual_review", {})
    assert result["status"] == "failed"
    assert "V00" in result["missing_gates"]
```

- [ ] **Step 2: Run tests and verify import failure**

Run: `pytest tests/test_harness_profiles.py -q`

Expected: FAIL because `buaa_thesis_kit.harness.profiles` does not exist.

- [ ] **Step 3: Implement immutable profile evaluation**

```python
@dataclass(frozen=True)
class HarnessProfile:
    name: str
    required_gates: tuple[str, ...]
    optional_gates: tuple[str, ...]


def evaluate_profile(name: str, gate_board: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    profile = load_profile(name)
    missing = [gate for gate in profile.required_gates if gate not in gate_board]
    failed = [gate for gate in profile.required_gates if gate_board.get(gate, {}).get("status") == "failed"]
    review = [gate for gate in profile.required_gates if gate_board.get(gate, {}).get("status") in {"needs_review", "todo"}]
    status = "failed" if missing or failed else "needs_review" if review else "pass"
    return {"profile": name, "status": status, "missing_gates": missing, "failed_gates": failed, "review_gates": review}
```

Define separate gate lists for `latex_pdf`, `word_editable`, `agent_visual_review`, and `legacy_word_layout`. Do not change the status of any source gate and do not make required LaTeX gates optional.

- [ ] **Step 4: Run focused and existing Harness tests**

Run:

```powershell
pytest tests/test_harness_profiles.py tests/test_harness.py tests/test_harness_progress.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit Harness profiles**

```powershell
git add buaa_thesis_kit/harness/profiles.py buaa_thesis_kit/harness/config/profiles.yaml tests/test_harness_profiles.py
git commit -m "feat: add independent thesis harness profiles"
```

### Task 5: Validate Agent Delivery Bundles

**Files:**
- Create: `buaa_thesis_kit/harness/delivery.py`
- Create: `scripts/validate_agent_delivery.py`
- Modify: `tests/test_harness_profiles.py`

- [ ] **Step 1: Add failing output-contract tests**

Test a bundle containing `thesis.pdf`, `thesis.tex`, `model.json`, `report.md`, `failure_queue.json`, `image/visual_review.json`, and a supplied gate board. Assert that a missing `thesis.pdf`, mismatched SHA256, unresolved visual page, or failed required gate makes the delivery fail. Assert that extra process files such as `standalone.tex` and `compile.log` are reported.

- [ ] **Step 2: Run tests and verify the missing API failure**

Run: `pytest tests/test_harness_profiles.py -q`

Expected: FAIL importing `validate_delivery`.

- [ ] **Step 3: Implement the minimal delivery validator**

Expose:

```python
def validate_delivery(
    output_dir: Path,
    *,
    profile: str,
    gate_board_path: Path,
    candidate_path: Path | None = None,
) -> dict[str, Any]:
    ...
```

The report must include source and output identities, profile result, missing artifacts, forbidden process artifacts, unresolved visual checks, and a normalized failure queue. The CLI writes JSON only to the explicit `--out` path so the Agent can use a temporary location and keep the public output clean.

- [ ] **Step 4: Run focused tests and CLI help**

Run:

```powershell
pytest tests/test_harness_profiles.py -q
python scripts/validate_agent_delivery.py --help
```

Expected: tests pass and help documents `--output`, `--profile`, `--gate-board`, `--candidate`, and `--out`.

- [ ] **Step 5: Commit the delivery validator**

```powershell
git add buaa_thesis_kit/harness/delivery.py scripts/validate_agent_delivery.py tests/test_harness_profiles.py
git commit -m "feat: validate agent thesis delivery bundles"
```

### Task 6: Re-run Agent Scenarios With the Skill

**Files:**
- Create: `tests/skill_evals/with_skill.json`
- Modify: `skills/normalizing-buaa-theses/SKILL.md` only if an observed loophole requires a minimal correction

- [ ] **Step 1: Run the same three scenarios with the new Skill loaded**

Do not include expected answers in the Agent prompt. Give the Agent only the scenario and the Skill. Record exact answers and decision checks in `tests/skill_evals/with_skill.json`.

- [ ] **Step 2: Verify all scenarios are green**

Run:

```powershell
python -c "import json; p=json.load(open('tests/skill_evals/with_skill.json',encoding='utf-8')); assert p['scenarios'] and all(x['passed'] for x in p['scenarios'])"
```

Expected: exit code `0`.

- [ ] **Step 3: Close only observed loopholes and rerun**

If an Agent bypasses XML priority, treats OCR as authoritative, or claims pass over a failed gate, add one explicit sentence addressing that observed behavior and rerun the same scenario. Do not add hypothetical process rules.

- [ ] **Step 4: Commit evaluation evidence**

```powershell
git add skills/normalizing-buaa-theses/SKILL.md tests/skill_evals/with_skill.json
git commit -m "test: verify thesis normalization skill behavior"
```

### Task 7: Real DOCX and PDF Acceptance

**Files:**
- Create: `docs/acceptance/2026-07-10-agent-skill-report.json`
- Create: `docs/acceptance/2026-07-10-agent-skill.md`
- Modify: `docs/AGENT_SKILL_WORKFLOW.md`

- [ ] **Step 1: Run the DOCX scenario through the Agent Skill**

Use `C:/Users/admin/Desktop/删减毕设.docx`. The Agent must record the source SHA256, read DOCX XML before any PDF conversion, generate the model, render through BUAAthesis, inspect required pages, and run the `latex_pdf` and `agent_visual_review` profiles.

- [ ] **Step 2: Run the PDF evidence scenario**

Use `C:/Users/admin/Desktop/崔润昊毕设打印版.pdf` for extraction and visual/equation behavior. Confirm that uncertain visual formulas remain `needs_review` rather than being silently promoted.

- [ ] **Step 3: Validate the final bundle**

Run:

```powershell
python scripts/validate_agent_delivery.py --output output --profile latex_pdf --gate-board tmp/skill_acceptance/harness/gate_board.json --candidate "C:/Users/admin/Desktop/删减毕设.docx" --out tmp/skill_acceptance/delivery_report.json
pytest tests -q
python -m compileall -q buaa_thesis_kit scripts
git diff --check
```

Expected: code tests and compile checks pass. The delivery may be `needs_review` only when every unresolved item is listed with evidence; it must not be reported as `pass` while formula, visual, or required gate failures remain.

- [ ] **Step 4: Inspect representative rendered pages**

Open and record page-level results for cover, task book, Chinese abstract, English abstract, TOC, body page 1, pages containing equations/figures, and references. `docs/acceptance/2026-07-10-agent-skill-report.json` must map each reviewed page to its final `output/image/` screenshot and status. Intermediate screenshots remain under `tmp/skill_acceptance/` and are deleted after the required evidence is copied.

- [ ] **Step 5: Document Agent usage and optional tools**

`docs/AGENT_SKILL_WORKFLOW.md` must show how an Agent loads the Skill, how it chooses tools based on capabilities, how Harness profiles are run, and why local OCR is optional. It must not present `run_equation_pipeline.py` or `setup_equation_ocr.py` as the main workflow.

- [ ] **Step 6: Commit acceptance evidence and documentation**

```powershell
git add docs/AGENT_SKILL_WORKFLOW.md docs/acceptance/2026-07-10-agent-skill.md docs/acceptance/2026-07-10-agent-skill-report.json
git commit -m "docs: record agent thesis skill acceptance"
```

### Task 8: Final Review and Safe Cleanup

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Delete: repository-local OCR virtual environment and obsolete equation spike outputs only after path and ownership checks

- [ ] **Step 1: Update the repository entry point**

Make README point to `skills/normalizing-buaa-theses/SKILL.md` as the primary Agent workflow. Keep command-line renderers under an optional tools heading.

- [ ] **Step 2: Audit generated disk usage inside this worktree**

Run a size report for `.venv-equation-ocr`, `output/equation_native*`, and formula-specific `tmp/` directories. Resolve every deletion target to an absolute path and verify it is inside this worktree before removal.

- [ ] **Step 3: Remove obsolete local OCR environment and spike artifacts**

Remove only the formula OCR virtual environment and outputs created by this branch. Preserve final acceptance artifacts, user files, templates, and unrelated dirty work. Keep optional OCR adapter source only if referenced as an optional tool.

- [ ] **Step 4: Run final verification**

Run:

```powershell
python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\normalizing-buaa-theses
pytest tests -q
python -m compileall -q buaa_thesis_kit scripts
git diff --check
git status --short --branch
```

Expected: Skill validation and tests pass, compile and diff checks are clean, and unrelated existing changes remain untouched.

- [ ] **Step 5: Commit entry-point and cleanup metadata**

```powershell
git add README.md .gitignore
git commit -m "docs: make agent thesis skill the primary workflow"
```
