from pathlib import Path

from buaa_thesis_kit.harness.validators import validate_model_file, validate_output_text_file, validate_render_file


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bad_outputs" / "thesis6.docx"
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


def test_current_thesis6_output_text_fails():
    report = validate_output_text_file(FIXTURE)

    assert report["status"] == "failed"
    reason_ids = {item["id"] for item in report["failures"]}
    assert "cover_classification_split" in reason_ids
    assert "cn_abstract_contains_english_title" in reason_ids
    assert "toc_contains_declaration" in reason_ids
    assert "toc_contains_template_sample_reference" in reason_ids
    assert "body_contains_template_page_number_48" in reason_ids
    assert "template_instructions_or_sample_leak" in reason_ids


def test_current_thesis6_render_fails_with_required_reasons(tmp_path):
    report = validate_render_file(candidate=FIXTURE, out_dir=tmp_path / "render_diff", sample_mode="truncated")

    assert report["status"] == "failed"
    reason_ids = {item["id"] for item in report["failures"]}
    assert {
        "cover_classification_split",
        "title_line_break_bad",
        "cn_abstract_contains_english_title",
        "toc_contains_declaration",
        "toc_contains_template_sample_reference",
        "body_contains_template_page_number_48",
        "template_instructions_or_sample_leak",
    }.issubset(reason_ids)


def test_reference_good_output_text_passes():
    report = validate_output_text_file(FIXTURE_ROOT / "reference_good.docx")

    assert report["status"] == "pass"
    assert report["failures"] == []


def test_truncated_sample_does_not_fail_for_missing_late_sections():
    docx_report = validate_output_text_file(FIXTURE_ROOT / "truncated_input.docx")
    model_report = validate_model_file(
        FIXTURE_ROOT / "expected_model_truncated.json",
        FIXTURE_ROOT / "expected_model_truncated.json",
        sample_mode="truncated",
    )

    assert docx_report["status"] == "pass"
    assert model_report["status"] == "pass"
