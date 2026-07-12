from pathlib import Path


def test_resolve_word_template_requires_valid_instrumented_template(tmp_path, monkeypatch):
    import buaa_thesis_kit.pipeline as pipeline

    valid_template = Path("templates/official/buaa_undergraduate_template_instrumented.docx")
    monkeypatch.setattr(pipeline, "DEFAULT_DOCX_TEMPLATE", valid_template)

    assert pipeline._resolve_word_template(None) == valid_template

    monkeypatch.setattr(
        pipeline,
        "validate_instrumented_template_file",
        lambda path: {"status": "failed", "failures": [{"id": "template_instruction_leak"}]},
    )

    try:
        pipeline._resolve_word_template(None)
    except ValueError as exc:
        assert "Instrumented template validation failed" in str(exc)
    else:
        raise AssertionError("invalid instrumented template must block pipeline")
