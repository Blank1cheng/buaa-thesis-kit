# BUAA Thesis Kit

北航本科毕业设计（论文）格式规范化工具包。目标是把 `.doc`、`.docx` 或 `.pdf`
论文输入，经过可诊断、可回环的 Agent Graph 流水线，输出符合交付约束的 Word、PDF、
TeX 和图片目录。

## 核心策略

当前流水线采用 `repair-first`：

1. 优先复制并修复源 Word，尽量保留原文档版面、正文结构、图片、表格和公式对象。
2. 对 PDF 输入，先抽取可编辑文本、封面元数据和结构边界，再套用同一套 Word 模板生成可编辑 DOCX；不得把整页截图作为最终 Word 正文。
3. 对缺失的规范项生成类型化 finding，例如 `missing_spine`、`spine_metadata_missing`。
4. 修复失败或视觉/合规判断未收敛时，通过 graph 回环重试；超过上限后失败退出。
5. 过程文件默认写入临时目录并删除，最终公开目录只保留验收产物。

## Graph 节点

```text
ingest
  -> profile_reference
  -> inspect_source
  -> diagnose_compliance
  -> plan_minimal_fixes
  -> apply_word_fixes
  -> export_pdf
  -> visual_compare
  -> decide
       pass -> finalize_output
       fail -> revise_plan -> apply_word_fixes
```

其中 `书脊` 是强制合规对象。源文档缺少书脊时，graph 会记录 `missing_spine`，
规划 `insert_spine`，在 Word 副本中插入可打印书脊页，并在 `report.md` 中记录修复和
仍需人工复核的元数据字段。

## 输出约束

最终输出目录固定为：

```text
output/
  thesis.docx
  thesis.pdf
  thesis.tex
  report.md
  image/
```

`thesis.docx` 是权威版面来源；`thesis.pdf` 从 `thesis.docx` 导出；`thesis.tex`
是辅助结构化备份，用于复核和恢复，不作为主输出。

PDF 输入的 `thesis.docx` 仍必须是可编辑 Word：封面、书脊、任务书和正文用模板文本渲染。
页面截图只可作为 OCR 或人工复核证据，不进入最终 Word 正文。

## 结构化抽取

PDF 输入优先使用 layout-aware 文本抽取：从 `page.get_text("dict")` 读取每行文本的页码、
坐标、字体和字号，再解析为 thesis model。页眉、页脚、单独页码和目录项不会进入 BODY；
`摘    要`、`Abstract`、`关键词`、`Key Words` 进入 `front_matter`；目录由 Word/PDF
渲染链路重建，不从源 PDF 复制成正文。疑似 Word 域代码残留，例如 `MERGEFORMAT`、`公式章`
和 `下一章`，会转为公式复核项，不作为普通正文输出。调试时可用 `--keep-work` 查看临时
`pdf-structured-extraction.md`，最终 `output/` 不保留该过程文件。

## 使用方法

```powershell
python scripts/run_pipeline.py input.docx --out output
python scripts/run_pipeline.py input.doc --out output
python scripts/run_pipeline.py input.pdf --out output
python scripts/run_pipeline.py input.docx --out output --keep-work
python scripts/run_pipeline.py input.pdf --out output --strict
```

`--keep-work` 只用于调试，会保留与 `output/` 相邻的过程目录；默认运行会删除过程文件。
`--strict` 用于最终提交门禁：只要仍存在人工复核项或 `needs_review` 输出，就会生成
`strict_finalization_failed` 并返回非零退出码。

## 可编辑性验收

`output/report.md` 中的 `Editability Audit` 是判断 `thesis.docx` 是否可编辑的机器证据。
PDF 输入时，`page_screenshot_drawing_count` 必须为 `0`；页面截图只能作为 OCR 或人工复核证据，
不能进入最终 Word 正文。`editable_characters`、`paragraph_count`、`table_count`、`drawing_count`
和 `omml_equation_count` 用于辅助判断正文、表格、图像和公式是否以可编辑 Word 结构输出。`body_snippet_count`
和 `body_snippet_hits` 记录从源正文抽样出的文本片段是否能在最终 Word 中以可编辑文本命中；
若源正文片段完全未命中，说明正文可能被图片替代，必须阻断。若模型中已有可转换的 OMML 公式，
`expected_omml_equation_count` 必须小于等于最终 DOCX 包内真实 `m:oMath`/`m:oMathPara` 对象数量，
否则视为公式被文本、截图或占位符替代并阻断。

## 封面几何验收

`output/report.md` 中的 `PDF cover geometry` 记录封面元素坐标证据，至少包含
`cover_title_y`、`thesis_title_y`、`field_rows_y` 和 `date_y`。这些值用于检查封面标题、
论文题目、学院/专业/姓名/导师字段行和日期是否落在参考模板区间内；若出现
`pdf_cover_geometry` 阻断项，说明封面元素位置已经偏离模板，不得作为最终合格 PDF。

## OCR 证据账本

`output/report.md` 中的 `OCR Ledger` 记录扫描页和无可提取文本页。每条 ledger 至少包含页码、
`needs_ocr` 状态、证据图片、可提取字符数、置信度和是否需要复核。证据图片会复制到
`output/image/`，例如 `pdf-page-001.png`，但不会作为整页截图插入最终 Word 正文。
当本机 OCR 引擎返回文本时，ledger 状态为 `ocr_text_extracted`，识别文本会进入可编辑
Word/TeX 正文，证据图仍保留在 `output/image/` 供复核。
默认 OCR hook 使用 `pytesseract`/`Pillow` 和本机 Tesseract 可执行程序；缺少语言包或
可执行程序时不会阻断流水线，而是继续输出 `needs_ocr`。

## 公式证据账本

`output/report.md` 中的 `Equation Ledger` 记录每个公式在最终 Word 中的可编辑状态。`editable_omml`
表示可编辑 Word 公式，`editable_ole_object` 表示保留了可编辑 OLE/MathType 对象，`trusted_latex`
表示可由可信 LaTeX 结构恢复。PDF 文本层中的 safe linear equation，以及受支持的 `frac`/`sqrt`、
`sum`/`int`、Greek、`bmatrix`/`pmatrix`/`cases`
宏，只有在解析器能够完整转换为 OMML 时才标记为 `editable_omml`；`latex_needs_review` 表示公式样式文本已经进入账本但仍需要复核并
转换为可编辑 Word 公式。`preview_image_needs_review` 和 `manual_transcription_required` 不能静默通过，
必须由 agent 或人工转写成可编辑公式后再进入最终验收。`editable_omml` 不是账本文字声明，
最终验收会打开 DOCX 包检查真实 OMML 对象数量。

## 图表一致性验收

流水线会执行 `figure/table validation`：正文中的图题、表题和正文引用必须能匹配到对应图像或表格资产。
`figure_caption_without_asset`、`table_caption_without_asset`、`figure_reference_without_asset`
和 `table_reference_without_asset` 是阻断项，说明模板化输出可能漏图、漏表或错位。`duplicate_figure_number`
和 `duplicate_table_number` 也是阻断项；同一图题下的多个图片资产按组合图处理，不视为重复编号。
DOCX 输入会尝试把图片后最近的 `图/Fig.` 图题绑定到对应图片资产；无题注图片或无标题表格进入人工复核。

## 模板前置结构规则

最终 `thesis.docx` 必须由统一 Word 模板生成固定前置结构：封面、书脊、任务书、声明、中文摘要、英文摘要、目录、正文、致谢、参考文献、附录。PDF 输入不得把源目录复制为正文；目录必须由 Word TOC 域生成，并在导出 PDF 前通过 Word COM 更新。正文渲染时必须过滤已进入前置结构的任务书、声明、摘要、目录和封面元数据，避免重复出现在正文里。

前置页由 `buaa_thesis_kit/front_matter_renderer.py` 统一渲染，不再由普通正文段落流式堆叠。封面使用固定模板页和固定资源 `assets/buaa_seal.png`、`assets/buaa_wordmark.png`；中文题名会先拆成稳定两行，避免末尾单字换行。书脊使用 OOXML 竖排文本框 `w:textDirection="tbRl"`，不再输出横排“书脊”调试页。

中文摘要、英文摘要和目录使用独立 section：摘要/目录页脚为罗马页码，正文 section 从 `第 1 页` 重新编号。中文摘要页只包含中文题名、学生/指导老师、`摘    要`、中文摘要正文和 `关键词：`；英文题名、`Author:`、`Tutor:` 只能进入英文摘要页。

章节结构优先使用源文档的可编辑标题；当 DOCX 自动编号没有出现在段落文本中时，流水线可根据后续 `1.1`、`2.1` 等小节号恢复一级标题编号。类似 `第一章 绪论。本章介绍...` 的章末总结句应作为正文段落保留，不得误判成新的一级标题或触发分页。

## 最终正文禁入项

最终 Word 正文不得出现过程调试文本、本地资产路径或图片/公式占位痕迹，例如 `[Figure inserted]`、`[Figure requires review]`、`[Equation preview inserted]`、`.worktrees`、`D:\`、`.wmf`、`.emf`、`.png`。图片、OCR 和公式的不确定项必须进入 `output/report.md` 的 ledger 与 `output/image/` 证据目录，而不是混入正文。

参考文献标题必须使用 `参考文献`，不得输出独立英文标题 `References`。公式抽取失败时不能把拆碎的线性 token 连续写成普通正文；可信 OMML/OLE/可转换 LaTeX 才能进入可编辑公式，否则保留为复核项。

## 报告状态

- `pass`：必需输出存在，且没有阻断项或人工复核项。
- `needs_review`：输出存在，但公式、图片、参考文献、元数据、PDF 版面或 OCR 仍需复核。
- `failed`：提取、Word 修复、TeX 生成或 PDF 导出出现阻断失败。

## 验证

```powershell
python -m pytest tests -q
python scripts/run_pipeline.py "D:\Work\研二下\Skill\论文\崔润昊毕设打印版.docx" --out output
python scripts/run_pipeline.py "C:\Users\admin\Desktop\崔润昊毕设打印版.pdf" --out output
python scripts/validate_front_matter.py "C:\Users\admin\Desktop\删减毕设.docx" output\thesis.docx
```

真实样例中的公式和部分图片会被标记为 `needs_review`，这是预期行为：系统不会把不确定的
公式转换、图片位置、PDF 文本顺序或 OCR 缺口静默当作合格结果。
