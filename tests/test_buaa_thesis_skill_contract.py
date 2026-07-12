from pathlib import Path
import re

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
SKILL_DIR = REPO_ROOT / "skills" / "normalizing-buaa-theses"
SKILL_PATH = SKILL_DIR / "SKILL.md"
REFERENCES_DIR = SKILL_DIR / "references"


def read_skill() -> str:
    assert SKILL_PATH.is_file(), f"missing main skill: {SKILL_PATH}"
    return SKILL_PATH.read_text(encoding="utf-8")


def read_readme() -> str:
    assert README_PATH.is_file(), f"missing README: {README_PATH}"
    return README_PATH.read_text(encoding="utf-8")


def parse_skill_frontmatter() -> dict[str, object]:
    frontmatter = re.match(
        r"\A---[ \t]*\r?\n(?P<body>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
        read_skill(),
        re.DOTALL,
    )
    assert frontmatter, "SKILL.md must begin with YAML frontmatter"

    metadata = yaml.safe_load(frontmatter.group("body"))
    assert isinstance(metadata, dict), "SKILL.md frontmatter must be a YAML mapping"
    return metadata


def parse_yaml_file(path: Path) -> dict[str, object]:
    assert path.is_file(), f"missing YAML file: {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} must contain a YAML mapping"
    return data


def read_reference(filename: str) -> str:
    path = REFERENCES_DIR / filename
    assert path.is_file(), f"missing reference: {path}"
    return path.read_text(encoding="utf-8")


def test_skill_frontmatter_and_agent_manifest_exist() -> None:
    metadata = parse_skill_frontmatter()

    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == "normalizing-buaa-theses"
    assert isinstance(metadata["description"], str)
    assert metadata["description"].startswith("Use when")

    agent_manifest = parse_yaml_file(SKILL_DIR / "agents" / "openai.yaml")
    interface = agent_manifest.get("interface")
    assert isinstance(interface, dict), "agents/openai.yaml must define interface"
    for field in ("display_name", "short_description"):
        value = interface.get(field)
        assert isinstance(value, str) and value.strip(), (
            f"agents/openai.yaml interface.{field} must be a non-empty string"
        )


@pytest.mark.parametrize(
    "required_token",
    [
        "DOCX XML",
        "Agent visual",
        "Harness",
        "failure_queue.json",
        "Do not claim pass",
    ],
)
def test_main_skill_contains_required_workflow_tokens(required_token: str) -> None:
    assert required_token in read_skill()


@pytest.mark.parametrize(
    ("behavior", "accepted_phrases"),
    [
        (
            "capability detection",
            ("capability detection", "detect capabilities", "capability check"),
        ),
        ("evidence model", ("evidence model", "evidence-based model")),
        ("BUAAthesis", ("BUAAthesis", "BUAA thesis class")),
        (
            "one failure",
            ("one failure at a time", "single failure per iteration", "fix one failure"),
        ),
        (
            "cleanup",
            ("cleanup stale artifacts", "cleanup generated artifacts", "cleanup outputs"),
        ),
    ],
)
def test_main_skill_defines_required_behaviors(
    behavior: str,
    accepted_phrases: tuple[str, ...],
) -> None:
    normalized_skill = read_skill().casefold()

    assert any(phrase.casefold() in normalized_skill for phrase in accepted_phrases), (
        f"SKILL.md must define {behavior}; expected one of {accepted_phrases}"
    )


def test_main_skill_does_not_reference_equation_ocr_setup_script() -> None:
    assert "setup_equation_ocr.py" not in read_skill()


def test_required_reference_documents_exist() -> None:
    required_references = {
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
    actual_references = (
        {path.name for path in REFERENCES_DIR.iterdir() if path.is_file()}
        if REFERENCES_DIR.is_dir()
        else set()
    )

    assert required_references <= actual_references


@pytest.mark.parametrize(
    "required_output",
    [
        "output/thesis.docx",
        "output/thesis.pdf",
        "output/thesis.tex",
        "output/model.json",
        "output/report.md",
        "output/failure_queue.json",
        "output/image/",
    ],
)
def test_output_contract_lists_required_artifacts(required_output: str) -> None:
    assert required_output in read_reference("output-contract.md")


def test_visual_validation_defines_manifest_schema_and_page_evidence_rules() -> None:
    reference = read_reference("visual-validation.md")
    normalized = reference.casefold()

    for token in (
        "visual_review.json",
        "pdf_sha256",
        "pdf_page_count",
        "region",
        "pages",
        "screenshot",
        "bbox",
        "status",
        "checks",
        "failure_ids",
    ):
        assert token in normalized
    assert re.search(
        r"(?:each|every)\s+page[^.\n]{0,120}(?:independent|separate)[^.\n]{0,80}screenshot"
        r"|(?:independent|separate)\s+screenshot[^.\n]{0,120}(?:each|every)\s+page",
        normalized,
    ), "visual-validation.md must require an independent screenshot for every page"
    assert re.search(
        r"(?:all|every)\s+(?:pdf\s+)?pages?[^.\n]{0,100}(?:cover|coverage)"
        r"|(?:full|complete)\s+(?:page|pdf page)\s+coverage",
        normalized,
    ), "visual-validation.md must require full PDF page coverage"
    assert re.search(
        r"non[- ]?pass[^.\n]{0,160}(?:active\s+)?failure_queue"
        r"|(?:active\s+)?failure_queue[^.\n]{0,160}non[- ]?pass",
        normalized,
    ), "non-pass visual failure IDs must enter the active failure queue"


def test_output_contract_defines_report_artifact_identity_digest() -> None:
    reference = read_reference("output-contract.md")
    normalized = reference.casefold()

    for token in (
        "artifact identity",
        "source_candidate_path",
        "source_sha256",
        "source_size",
        "artifact_manifest_sha256",
    ):
        assert token in normalized
    assert re.search(
        r"(?:exclude|excluding|excluded|omit|omits)\s+`?report\.md`?"
        r"[^.\n]{0,160}(?:cycle|circular)"
        r"|(?:cycle|circular)[^.\n]{0,160}(?:exclude|excluding|excluded|omit|omits)"
        r"[^.\n]{0,80}`?report\.md`?",
        normalized,
    ), "artifact manifest digest must exclude report.md to avoid a digest cycle"


def test_failure_taxonomy_defines_semantic_ids_and_resolved_history() -> None:
    reference = read_reference("failure-taxonomy.md")
    normalized = reference.casefold()

    for token in ("semantic key", "h-g28-cover-review", "resolved history"):
        assert token in normalized
    assert re.search(
        r"(?:h-id|failure id|id)[^.\n]{0,160}(?:not|never|must not)"
        r"[^.\n]{0,100}(?:evidence|appearance order|occurrence order)"
        r"|(?:evidence|appearance order|occurrence order)[^.\n]{0,120}"
        r"(?:does not|must not|never)[^.\n]{0,100}(?:determine|define|change)[^.\n]{0,60}(?:h-id|failure id|id)",
        normalized,
    ), "H-ID must not be derived from evidence or failure appearance order"


def test_failure_taxonomy_uses_sha256_and_forbids_sequence_allocated_ids() -> None:
    reference = read_reference("failure-taxonomy.md")
    normalized = reference.casefold()

    assert re.search(
        r"evidence\.sha256|(?:^|\s)sha256(?:\s|:|`)",
        normalized,
        re.MULTILINE,
    ), "failure evidence schema must name sha256"
    assert "h-<gate>-<序号>" not in normalized
    assert not re.search(
        r"(?:appearance|occurrence)\s+(?:order|sequence)[^.\n]{0,100}"
        r"(?:assign|allocate|allocation)"
        r"|(?:assign|allocate)[^.\n]{0,100}(?:appearance|occurrence)\s+"
        r"(?:order|sequence)",
        normalized,
    ), "H-IDs must not be allocated by failure appearance order"
    assert "semantic key" in normalized
    assert "h-g28-cover-review" in normalized


def test_failure_taxonomy_requires_concrete_ids_in_agent_reports() -> None:
    reference = read_reference("failure-taxonomy.md")
    normalized = reference.casefold()

    assert re.search(
        r"(?:must|always)[^.\n]{0,120}(?:concrete|explicit|actual)\s+h-id"
        r"|(?:concrete|explicit|actual)\s+h-id[^.\n]{0,120}(?:must|always)",
        normalized,
    ), "Agent reports must instantiate concrete H-IDs instead of promising one later"
    for expected_id in (
        "h-g23-xelatex-unresolved-control-sequence",
        "h-g27-visual-review-open",
        "h-g28-references-right-overflow",
        "h-g26-equation-2-3-symbol-ambiguity",
    ):
        assert expected_id in normalized


def test_failure_taxonomy_requires_queue_records_for_observed_gates() -> None:
    reference = read_reference("failure-taxonomy.md")
    normalized = reference.casefold()

    assert re.search(
        r"gate[- ]board[^.\n]{0,220}failure_queue"
        r"|failure_queue[^.\n]{0,220}gate[- ]board",
        normalized,
    )
    for field in ("id", "gate", "status", "evidence", "suggested_fix"):
        assert field in normalized


def test_equation_review_bundle_is_not_final_delivery() -> None:
    reference = read_reference("equation-handling.md")
    normalized = reference.casefold()

    assert re.search(
        r"needs_review[^.\n]{0,220}(?:must not|never|不得)[^.\n]{0,120}"
        r"(?:final delivery|最终交付|正式交付)"
        r"|(?:final delivery|最终交付|正式交付)[^.\n]{0,220}"
        r"(?:must not|never|不得)[^.\n]{0,120}needs_review",
        normalized,
    )


def test_unknown_degree_must_not_be_guessed() -> None:
    skill = read_skill()

    assert re.search(
        r"(?:do not|must not|never)\s+guess[^.\n]*degree"
        r"|degree[^.\n]*(?:do not|must not|never)\s+guess",
        skill,
        re.IGNORECASE,
    ), "SKILL.md must forbid guessing an undetermined degree"


def test_equation_handling_defines_source_priority_and_optional_external_ocr() -> None:
    equation_handling = read_reference("equation-handling.md").casefold()

    for required_token in (
        "omml",
        "mtef",
        "verified text",
        "agent visual",
        "external ocr",
    ):
        assert required_token in equation_handling
    assert re.search(
        r"external\s+ocr[^.\n!?]{0,120}(?:not required|optional)"
        r"|(?:not required|optional)[^.\n!?]{0,120}external\s+ocr",
        equation_handling,
    ), "external OCR must be explicitly described as optional or not required"

    priority_marker = re.search(
        r"priority|precedence|preferred order|source order",
        equation_handling,
    )
    assert priority_marker, "equation-handling.md must label the source priority"
    priority_section = equation_handling[priority_marker.end() : priority_marker.end() + 600]
    source_positions = {
        source: priority_section.find(source)
        for source in (
            "omml",
            "mtef",
            "verified text",
            "agent visual",
            "external ocr",
        )
    }
    assert all(position >= 0 for position in source_positions.values()), (
        "the priority section must list OMML, MTEF, verified text, Agent visual, "
        "and external OCR"
    )
    assert max(source_positions["omml"], source_positions["mtef"]) < source_positions[
        "verified text"
    ]
    assert (
        source_positions["verified text"]
        < source_positions["agent visual"]
        < source_positions["external ocr"]
    ), (
        "equation source priority must place OMML and MTEF before verified text, "
        "then Agent visual, then external OCR"
    )


def test_equation_handling_documents_hash_bound_agent_review_ledger() -> None:
    reference = read_reference("equation-handling.md").casefold()

    for token in (
        "--equation-review",
        "agent_visual",
        "candidate.tex",
        "source_preview.png",
        "rendered.png",
        "correction_reason",
        "corrected_latex_sha256",
    ):
        assert token in reference
    assert "source_sha256" in reference


def test_output_contract_documents_flat_packaging_and_independent_validation() -> None:
    reference = read_reference("output-contract.md")
    normalized = reference.casefold()

    for token in (
        "scripts/package_agent_delivery.py",
        "scripts/validate_agent_delivery.py",
        "--visual-manifest",
        "--gate-board",
        "model.json source",
    ):
        assert token.casefold() in normalized
    assert re.search(
        r"(?:inline|flatten)[^\n]{0,180}(?:\\include\{data|generated tex fragments)"
        r"|(?:\\include\{data|generated tex fragments)[^\n]{0,180}(?:inline|flatten)",
        normalized,
    )
    assert re.search(
        r"(?:fresh|new|重新|全新)[^.\n]{0,160}(?:compile|编译)[^.\n]{0,220}(?:pixel|像素|page count|页数)",
        normalized,
    )


def test_readme_exposes_only_the_current_latex_first_delivery_workflow() -> None:
    readme = read_readme()
    normalized = readme.casefold()

    for token in (
        "scripts/run_latex_pipeline.py",
        "scripts/package_agent_delivery.py",
        "scripts/validate_agent_delivery.py",
        "skills/normalizing-buaa-theses/skill.md",
        "output/failure_queue.json",
        "output/image/visual_review.json",
    ):
        assert token.casefold() in normalized
    assert "thesis.docx 是权威版面来源" not in readme
    assert "output/template_inheritance_report.json" not in normalized
