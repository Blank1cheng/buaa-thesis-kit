# Agent 工作流

## 1. 接收与备份

先复制源 Word/PDF 到工作区，保留原文件不改。若同时有 Word 和 PDF，以 Word 为权威源；若只有 Word，则最终 PDF 从 Word 导出；若只有 PDF，先做文本、元数据和结构抽取，再套用统一 Word 模板生成可编辑 DOCX，并在报告中标记布局、公式和图表复核风险。

## 2. 结构识别

按规则加载器读取章节、元数据、图表、公式、参考文献规则。先识别封面、任务书、声明、摘要、目录、正文、参考文献，再处理样式。PDF 输入必须保留每行文本的页码、坐标、字体和字号证据，先过滤页眉页脚、单独页码和目录项，再把 `摘    要`、`Abstract`、`关键词`、`Key Words` 放入 `front_matter`。`MERGEFORMAT`、`公式章`、`下一章` 等域代码残留不得进入普通正文，必须转为公式复核项。章节边界不确定时，不要猜测移动大段内容，改为人工复核。

## 3. 模板填充

使用 `templates/buaa_undergraduate_thesis_template.docx` 生成权威 Word 输出，使用 `templates/buaa_undergraduate_thesis_template.tex` 生成辅助 TeX。PDF 输入也必须生成可编辑 Word：封面、书脊、任务书和正文由模板文本渲染，不得把整页 PDF 截图嵌入最终 Word。中文摘要页使用 `摘    要` 和 `关键词：`，英文摘要页使用 `Abstract` 和 `Key Words:`，中英文摘要必须分页。图片和公式截图等资源统一放入 `output/image`，Word 内嵌资源，TeX 使用相对路径。

## 4. 校验与报告

生成 `output/report.md` 时记录每个关键元数据字段的置信度和证据；列出自动修改、警告、阻断项、人工复核项。报告中必须说明 Word 为权威源、PDF 从 Word 导出，避免用户误以为 TeX 是主输出。

## 5. 最终交付

只公开以下路径：`output/thesis.docx`、`output/thesis.pdf`、`output/thesis.tex`、`output/report.md`、`output/image/`。交付前检查 DOCX 可打开、PDF 来自最新 Word、TeX 无乱码、图片路径有效、报告无空白占位。

## 6. Editability Audit and strict finalization

Every run must preserve `output/thesis.docx` as the authoritative editable Word document. Agents must inspect the `Editability Audit` section in `output/report.md` before claiming a PDF-derived Word file is usable. For a PDF input, `page_screenshot_drawing_count` must be `0`; page renders may exist only as OCR or manual-review evidence, not as final Word body pages. `body_snippet_count` and `body_snippet_hits` must show that sampled source body text is present as editable Word text; `editable_body_text_missing` means the Word output may have replaced source body content with raster images and must not be accepted.

Use `--strict` for final submission checks. In strict finalization mode, any manual-review item or `needs_review` output must produce `strict_finalization_failed`, and the CLI must exit non-zero. Non-strict mode may still emit `needs_review` so reviewers can inspect editable Word, PDF, TeX, and image outputs.

## 7. PDF cover geometry

Every exported PDF must pass `PDF cover geometry` validation before final submission. Agents should inspect `cover_title_y`, `thesis_title_y`, `field_rows_y`, and `date_y` in `output/report.md`; these values must stay within the reference-template bands for the cover title, thesis title, cover metadata rows, and date. A `pdf_cover_geometry` blocking item means the cover layout has drifted and the Word template spacing must be repaired before acceptance.

## 8. OCR Ledger

For scanned PDF pages or pages with no extractable text, the pipeline must render a page evidence image such as `pdf-page-001.png`, copy it to `output/image/`, and write an `OCR Ledger` entry in `output/report.md`. Each entry should carry the page number, `needs_ocr` or `ocr_text_extracted` status, evidence image, extracted character count, confidence, and review flag. When OCR text is extracted, agents may render that text into editable Word/TeX body content while keeping the page image only as evidence. The evidence image must not be inserted as a full-page Word screenshot.

## 9. Equation Ledger

Every run must write an `Equation Ledger` entry for each detected equation. `editable_omml` and `editable_ole_object` may remain in the final Word because they are editable Word/OLE objects. `trusted_latex` may be regenerated as editable math only when the extractor marks it trusted. A safe linear PDF text equation, including supported `frac`, `sqrt`, `sum`, `int`, Greek macros, and `bmatrix`/`pmatrix`/`cases` environments, may be marked `editable_omml` only when the parser fully converts it to OMML; unsupported text-layer equations must remain `latex_needs_review`. `latex_needs_review` means PDF text extraction found an equation-like line and preserved a LaTeX-like string, but it still needs review and editable Word equation conversion. `preview_image_needs_review` and `manual_transcription_required` are not compliant final states; agents must convert them to editable Word equations or keep the run in `needs_review`. Preview images may be copied to `output/image/` as evidence, but they must not be treated as editable equations.

## 10. Figure/Table validation

Every run must perform `figure/table validation` before acceptance. `figure_caption_without_asset`, `table_caption_without_asset`, `figure_reference_without_asset`, and `table_reference_without_asset` are blocking items because they indicate that a caption or body reference may have lost its editable image/table asset during template rendering. `duplicate_figure_number` and `duplicate_table_number` are also blocking items, except that multiple image assets with the same normalized figure number and the same caption are treated as one composite figure. For DOCX input, agents should bind a picture to the nearest following `图/Fig.` caption when possible. Uncaptioned figure assets and untitled tables should remain in manual review until the caption/title can be reconciled.
