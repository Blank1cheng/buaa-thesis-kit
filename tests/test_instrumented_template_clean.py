from pathlib import Path


def test_validate_instrumented_template_rejects_dirty_template(tmp_path):
    from scripts.validate_instrumented_template import validate_instrumented_template

    dirty_template = Path("templates/official/buaa_undergraduate_template_instrumented.docx")
    report_path = tmp_path / "instrumented_template_report.json"

    report = validate_instrumented_template(dirty_template, report_path)

    assert report["status"] == "pass"
    assert report["failures"] == []
    assert report["checks"]["toc_field"] is True
    assert report["checks"]["page_number_fields"] is True
    assert report["checks"]["headers_footers"] is True
    assert report["checks"]["static_template_page_48"] is True
    assert report["checks"]["toc_result_clean"] is True
    assert report["checks"]["frontmatter_not_in_toc"] is True
    assert report_path.exists()
