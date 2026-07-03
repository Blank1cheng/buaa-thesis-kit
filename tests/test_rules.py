import re

import pytest

from buaa_thesis_kit import rules as rules_module
from buaa_thesis_kit.rules import load_all_rules, load_rule_file


EXPECTED_RULE_FILES = (
    "format-rules.yaml",
    "metadata-extraction-rules.yaml",
    "section-splitting-rules.yaml",
    "figure-table-rules.yaml",
    "equation-rules.yaml",
    "reference-rules.yaml",
)


def test_load_metadata_rules():
    rules = load_rule_file("metadata-extraction-rules.yaml")

    assert "metadata_fields" in rules
    assert "student_name" in rules["metadata_fields"]
    assert rules["metadata_fields"]["unit_code"]["default"] == "10006"


def test_load_all_rules_contains_required_groups():
    rules = load_all_rules()

    for key in EXPECTED_RULE_FILES:
        assert key in rules


def test_rule_file_names_are_whitelisted():
    assert rules_module.RULE_FILES == EXPECTED_RULE_FILES


def test_load_all_rules_uses_rule_files_whitelist(monkeypatch):
    monkeypatch.setattr(rules_module, "RULE_FILES", ("metadata-extraction-rules.yaml",))

    rules = rules_module.load_all_rules()

    assert list(rules) == ["metadata-extraction-rules.yaml"]


@pytest.mark.parametrize(
    "name",
    [
        "../schemas/metadata.schema.json",
        "rules/format-rules.yaml",
        r"rules\format-rules.yaml",
        str((rules_module.RULES_DIR / "format-rules.yaml").resolve()),
        "unknown.yaml",
    ],
)
def test_load_rule_file_rejects_invalid_names(name):
    with pytest.raises(ValueError):
        load_rule_file(name)


def test_yaml_parse_errors_include_filename_context(tmp_path, monkeypatch):
    (tmp_path / "broken.yaml").write_text("metadata_fields: [\n", encoding="utf-8")
    monkeypatch.setattr(rules_module, "RULES_DIR", tmp_path)
    monkeypatch.setattr(rules_module, "RULE_FILES", ("broken.yaml",), raising=False)

    with pytest.raises(ValueError) as exc_info:
        rules_module.load_rule_file("broken.yaml")

    assert "broken.yaml" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


def test_section_rules_distinguish_required_sections_from_canonical_order():
    rules = load_rule_file("section-splitting-rules.yaml")

    assert "required_order" not in rules
    assert rules["canonical_order"] == [
        "cover",
        "task_book",
        "declaration",
        "chinese_abstract",
        "english_abstract",
        "toc",
        "body",
        "acknowledgements",
        "references",
    ]
    assert "acknowledgements" not in rules["required_sections"]
    assert "references" in rules["required_sections"]


def test_configured_regex_patterns_compile():
    metadata_rules = load_rule_file("metadata-extraction-rules.yaml")
    section_rules = load_rule_file("section-splitting-rules.yaml")
    figure_table_rules = load_rule_file("figure-table-rules.yaml")
    reference_rules = load_rule_file("reference-rules.yaml")

    patterns = []
    patterns.extend(
        field["pattern"]
        for field in metadata_rules["metadata_fields"].values()
        if "pattern" in field
    )
    patterns.extend(section_rules["body_heading_patterns"].values())
    patterns.extend(figure_table_rules["figures"]["body_caption_patterns"])
    patterns.extend(figure_table_rules["tables"]["caption_patterns"])
    patterns.append(reference_rules["references"]["entry_pattern"])
    patterns.extend(reference_rules["references"]["citation_patterns"])

    for pattern in patterns:
        re.compile(pattern)


def test_decision_policy_exists_and_defines_statuses():
    policy = (rules_module.RULES_DIR / "decision-policy.md").read_text(encoding="utf-8")

    assert "`pass`" in policy
    assert "`needs_review`" in policy
    assert "`failed`" in policy


def test_agent_workflow_documents_editability_and_strict_finalization():
    root = rules_module.RULES_DIR.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    workflow = (root / "references" / "agent-workflow.md").read_text(encoding="utf-8")
    roadmap = (root / "references" / "phase-2-roadmap.md").read_text(encoding="utf-8")

    assert "Editability Audit" in readme
    assert "--strict" in readme
    assert "Editability Audit" in workflow
    assert "page_screenshot_drawing_count" in workflow
    assert "--strict" in workflow
    assert "strict_finalization_failed" in workflow
    assert "strict finalization mode" in roadmap


def test_agent_workflow_documents_ocr_ledger():
    root = rules_module.RULES_DIR.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    workflow = (root / "references" / "agent-workflow.md").read_text(encoding="utf-8")

    assert "OCR Ledger" in readme
    assert "needs_ocr" in readme
    assert "OCR Ledger" in workflow
    assert "needs_ocr" in workflow
    assert "pdf-page-001.png" in workflow
