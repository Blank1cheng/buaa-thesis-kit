from pathlib import Path

from buaa_thesis_kit.harness.validators import validate_output_text_file


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bad_outputs" / "thesis7.docx"


def test_thesis7_bad_fixture_fails_with_required_reasons():
    report = validate_output_text_file(FIXTURE)

    assert report["status"] == "failed"
    reason_ids = {item["id"] for item in report["failures"]}
    assert "template_instructions_or_sample_leak" in reason_ids
    assert "spine_template_instruction_leak" in reason_ids
    assert "toc_contains_declaration" in reason_ids
    assert "toc_contains_template_sample_reference" in reason_ids
    assert "body_contains_template_page_number_48" in reason_ids
    assert "cover_classification_split" in reason_ids
    assert "cn_abstract_contains_english_title" in reason_ids
