from buaa_thesis_kit.figure_table_acceptance import inspect_figure_tables
from buaa_thesis_kit.models import AssetItem, ContentBlock, ThesisModel


def test_inspect_figure_tables_blocks_caption_without_matching_figure_asset():
    model = ThesisModel(
        sections=[
            ContentBlock(
                id="section-1",
                type="chapter",
                title="1 Introduction",
                text="The system is shown below.\nFigure 1.1 System overview",
            )
        ],
        figures=[],
    )

    result = inspect_figure_tables(model)

    assert "figure_caption_without_asset: Figure 1.1" in result.blocking_items


def test_inspect_figure_tables_blocks_duplicate_figure_numbers():
    model = ThesisModel(
        sections=[
            ContentBlock(id="section-1", type="chapter", text="Figure 1.1 System overview")
        ],
        figures=[
            AssetItem(id="fig-1", type="image", path="figure-a.png", caption="Figure 1.1 System overview"),
            AssetItem(id="fig-2", type="image", path="figure-b.png", caption="Fig. 1.1 Duplicate view"),
        ],
    )

    result = inspect_figure_tables(model)

    assert "duplicate_figure_number: Figure 1.1" in result.blocking_items


def test_inspect_figure_tables_allows_multiple_assets_for_same_captioned_figure():
    model = ThesisModel(
        sections=[
            ContentBlock(id="section-1", type="chapter", text="图1.3 实验目标靶板")
        ],
        figures=[
            AssetItem(id="fig-1a", type="image", path="figure-a.png", caption="图1.3 实验目标靶板"),
            AssetItem(id="fig-1b", type="image", path="figure-b.png", caption="图1.3 实验目标靶板"),
        ],
    )

    result = inspect_figure_tables(model)

    assert not any("duplicate_figure_number" in item for item in result.blocking_items)


def test_inspect_figure_tables_marks_uncaptioned_figure_for_review():
    model = ThesisModel(
        figures=[AssetItem(id="fig-1", type="image", path="figure.png", caption="")]
    )

    result = inspect_figure_tables(model)

    assert result.blocking_items == []
    assert "uncaptioned_figure_asset: fig-1" in result.manual_review


def test_inspect_figure_tables_validates_tables_and_notes_success():
    model = ThesisModel(
        sections=[
            ContentBlock(
                id="section-1",
                type="chapter",
                text="As shown in Figure 1.1 and Table 1.1, the result is stable.\nFigure 1.1 System overview",
            )
        ],
        figures=[
            AssetItem(id="fig-1", type="image", path="figure.png", caption="Figure 1.1 System overview")
        ],
        tables=[
            ContentBlock(id="table-1", type="table", title="Table 1.1 Metrics", text="Metric\tValue")
        ],
    )

    result = inspect_figure_tables(model)

    assert result.blocking_items == []
    assert result.manual_review == []
    assert any("figure/table validation passed" in note for note in result.notes)


def test_inspect_figure_tables_does_not_treat_cjk_inline_references_as_captions():
    model = ThesisModel(
        sections=[
            ContentBlock(
                id="section-1",
                type="chapter",
                text="\u56fe2.3\u4e2d\u7684\u9640\u87ba\u4eea\u8f93\u51fa\u6570\u636e\u8868\u660e\u7cfb\u7edf\u7a33\u5b9a\u3002\n"
                "\u88682.1\u7684FMECA\u5206\u6790\u5217\u51fa\u4e86IMU\u4e2d\u53ef\u80fd\u9047\u5230\u7684\u9000\u5316\u6a21\u5f0f\u3002",
            )
        ],
        figures=[
            AssetItem(
                id="fig-23",
                type="image",
                path="figure-2-3.png",
                caption="\u56fe 2.3 IMU \u4eff\u771f\u6570\u636e\u56fe",
            )
        ],
        tables=[
            ContentBlock(
                id="table-21",
                type="table",
                title="\u8868 2.1 FMECA \u5206\u6790",
                text="\u9000\u5316\u6a21\u5f0f\t\u5f71\u54cd",
            )
        ],
    )

    result = inspect_figure_tables(model)

    assert result.blocking_items == []
