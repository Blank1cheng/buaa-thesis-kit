from buaa_thesis_kit.models import ContentBlock, ThesisModel
from buaa_thesis_kit.reference_acceptance import inspect_references


def test_inspect_references_blocks_missing_cited_reference_number():
    model = ThesisModel(
        sections=[
            ContentBlock(
                id="section-1",
                type="chapter",
                title="1 Introduction",
                text="The controller follows prior work [1] and the sensor model [3].",
            )
        ],
        references=[
            ContentBlock(id="ref-1", type="reference", text="[1] Wang. Flight control. 2026."),
            ContentBlock(id="ref-2", type="reference", text="[2] Smith. Data systems. 2025."),
        ],
    )

    result = inspect_references(model)

    assert "citation_without_reference: [3]" in result.blocking_items


def test_inspect_references_blocks_duplicate_reference_numbers():
    model = ThesisModel(
        sections=[
            ContentBlock(
                id="section-1",
                type="chapter",
                text="The method is consistent with prior studies [1].",
            )
        ],
        references=[
            ContentBlock(id="ref-1", type="reference", text="[1] Wang. Flight control. 2026."),
            ContentBlock(id="ref-2", type="reference", text="[1] Smith. Data systems. 2025."),
        ],
    )

    result = inspect_references(model)

    assert "duplicate_reference_number: [1]" in result.blocking_items


def test_inspect_references_marks_non_gbt_like_entries_for_review():
    model = ThesisModel(
        sections=[
            ContentBlock(id="section-1", type="chapter", text="The method is based on [1].")
        ],
        references=[
            ContentBlock(id="ref-1", type="reference", text="[1] Wang Flight control 2026")
        ],
    )

    result = inspect_references(model)

    assert result.blocking_items == []
    assert any("non_gbt_7714_entry" in item for item in result.manual_review)


def test_inspect_references_accepts_contiguous_citation_ranges():
    model = ThesisModel(
        sections=[
            ContentBlock(id="section-1", type="chapter", text="Related work is summarized in [1-3].")
        ],
        references=[
            ContentBlock(id="ref-1", type="reference", text="[1] Wang. Flight control. 2026."),
            ContentBlock(id="ref-2", type="reference", text="[2] Smith. Data systems. 2025."),
            ContentBlock(id="ref-3", type="reference", text="[3] Li. Sensor fusion. 2024."),
        ],
    )

    result = inspect_references(model)

    assert result.blocking_items == []
    assert any("reference validation passed" in note for note in result.notes)


def test_inspect_references_accepts_chinese_citation_separators():
    model = ThesisModel(
        sections=[
            ContentBlock(
                id="section-1",
                type="chapter",
                text="Related work uses Chinese citation separators [1\uFF0C3\u30014].",
            )
        ],
        references=[
            ContentBlock(id="ref-1", type="reference", text="[1] Wang. Flight control. 2026."),
            ContentBlock(id="ref-3", type="reference", text="[3] Li. Sensor fusion. 2024."),
            ContentBlock(id="ref-4", type="reference", text="[4] Zhao. Robust control. 2023."),
        ],
    )

    result = inspect_references(model)

    assert result.blocking_items == []


def test_inspect_references_ignores_zero_based_numeric_vectors():
    model = ThesisModel(
        sections=[
            ContentBlock(
                id="section-1",
                type="chapter",
                text="The static gyroscope vector is [0,0,0] rad/s.",
            )
        ],
    )

    result = inspect_references(model)

    assert result.blocking_items == []


def test_inspect_references_groups_pdf_reference_continuation_lines():
    model = ThesisModel(
        sections=[
            ContentBlock(id="section-1", type="chapter", text="The method is based on [1].")
        ],
        references=[
            ContentBlock(
                id="ref-1",
                type="reference",
                text="[1] Wang. Long reference title split by PDF extraction",
            ),
            ContentBlock(
                id="ref-1-cont",
                type="reference",
                text="Journal Name,2026,1(1):1-9.",
            ),
        ],
    )

    result = inspect_references(model)

    assert result.blocking_items == []
    assert result.manual_review == []
