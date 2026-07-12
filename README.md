# BUAA Thesis Kit

北航本科与硕士论文的 Agent-first 规范化工作流。输入 DOCX 或 PDF，先建立带证据的
`model.json`，再使用 BUAAthesis 原生模板生成 LaTeX/PDF。Agent 负责提取、公式判读和逐页视觉
复核；Harness 独立判断是否可以交付。

主入口是 [`skills/normalizing-buaa-theses/SKILL.md`](skills/normalizing-buaa-theses/SKILL.md)。
本地脚本是可选的确定性工具，不替代 Agent 取证，也不能覆盖 Harness 失败。

## 当前架构

```text
DOCX/PDF
  -> source identity (absolute path + size + SHA256)
  -> evidence-backed model.json
  -> extraction Harness
  -> native equation workflow
  -> BUAAthesis undergraduate/master renderer
  -> XeLaTeX PDF
  -> Agent page-by-page visual review
  -> Harness profiles
  -> flat public output/
```

- DOCX 输入优先读取原始 OOXML 中的 `w:t`、表格、文本框、OMML、OLE 和 relationships，
  不先转 PDF 再抽取。
- PDF 输入先读取字符、字体和 bbox，再结合页面截图核验。无法由独立证据消歧的公式或字段保持
  `needs_review`，不得猜测。
- PDF 正确性使用 BUAAthesis 的原生封面和前置页实现。Word renderer 仅作为 legacy/experimental
  编辑路径，不是当前 PDF 主流程。
- 本科使用 `undergraduate`，硕士使用 `master`。培养层次无法确认时停止套用模板。

## 环境

```powershell
python -m pip install -r requirements.txt
```

PDF 编译需要 XeLaTeX/latexmk。当前锁定模板位于
`templates/latex/buaa/bhosc/`，来源为
[BHOSC/BUAAthesis](https://github.com/BHOSC/BUAAthesis)。最终 `report.md` 会记录 class SHA、
class 版本、TeX Live/XeTeX/latexmk 版本、字体声明和最终 PDF 字体对象。

## 运行主流程

过程文件写入 `tmp/` 或其他临时目录，不直接写入公开 `output/`。

```powershell
python scripts/run_latex_pipeline.py thesis.docx `
  --buaa-template-path templates\latex\buaa\bhosc `
  --degree-type undergraduate `
  --out tmp\thesis_run
```

PDF 输入使用同一入口：

```powershell
python scripts/run_latex_pipeline.py thesis.pdf `
  --buaa-template-path templates\latex\buaa\bhosc `
  --degree-type undergraduate `
  --out tmp\thesis_run_pdf
```

主 run 会输出 extraction reports、G20-G28 gate board、稳定失败队列、候选 TeX 和编译 PDF。
`G27=needs_review` 表示语义或公式仍未闭环，不能称为最终交付。

## 公式复核

优先级为 `OMML/MTEF > verified text > Agent visual > optional external OCR`。每个公式均绑定稳定
ID、源 SHA、候选、来源裁剪、独立渲染和文件 SHA。Agent 完成逐符号比较后，可提交哈希绑定的
review ledger：

```powershell
python scripts/run_latex_pipeline.py thesis.docx `
  --buaa-template-path templates\latex\buaa\bhosc `
  --degree-type undergraduate `
  --out tmp\thesis_reviewed `
  --equation-review tmp\equation_review.json
```

修正候选必须记录 `correction_reason` 和 `corrected_latex_sha256`，并对修正后的候选重新执行
安全检查、最小 XeLaTeX 编译和来源裁剪视觉比较，更新 artifact hashes。公式截图只允许作为
审计证据，不得作为最终正文公式。

## 逐页视觉复核

将最终候选 PDF 的每一页分别渲染为真实 raster screenshot。Agent 检查封面、书脊、任务书、
声明、中英文摘要、目录、章首页、图表公式页、致谢/附录和参考文献，并写入：

```text
output/image/visual_review.json
```

清单必须绑定 `pdf_sha256` 和 `pdf_page_count`；每页一条独立记录，包含 `region`、`pages`、
`screenshot`、`bbox`、`status`、`checks` 和 `failure_ids`。任一 non-pass H-ID 必须同时存在于
active `output/failure_queue.json`。

## 兼容审计与主流程门禁

LaTeX-first 不会跳过既有的内容完整性检查。Agent 和 Harness 必须保留以下审计证据，并把
未闭环项映射到稳定 H-ID；这些记录不能被渲染器的成功退出码覆盖：

- `Editability Audit`：DOCX 输入检查正文仍是可编辑文本；PDF 输入提供最佳努力 DOCX 时，
  `page_screenshot_drawing_count` 必须为 `0`，且 `body_snippet_hits` 必须证明源正文片段存在。
  兼容 Word 流程的最终检查使用 `scripts/run_pipeline.py --strict`；任何人工复核项必须产生
  `strict_finalization_failed`。LaTeX 主流程采用等价的 required G/V gates。
- `OCR Ledger`：无文本层或扫描页记录 `needs_ocr`；只有 OCR 文字及页面证据一致时才记录
  `ocr_text_extracted`。OCR 页面图只能进入证据目录，不能伪装成可编辑正文。
- `Equation Ledger`：记录 `editable_omml`、`editable_ole_object`、可信原生 LaTeX 及审核哈希。
  PDF 的 safe linear 候选即使能够完整解析 `frac`、`sqrt`、`sum`、`int`、Greek 符号以及
  `bmatrix`、`pmatrix`、`cases`，仍只能保持 `latex_needs_review` 或
  `preview_image_needs_review`；PDF 文本层本身不是原生公式证据，不得自动接受或猜测。
- `PDF cover geometry`：视觉审计记录 `cover_title_y`、`field_rows_y` 和 `date_y`，并与对应
  本科或硕士 BUAAthesis 参考页比较。越界或层次错误必须失败。
- `figure/table validation`：标题、资源、编号和正文引用必须一致；
  `figure_caption_without_asset`、`duplicate_figure_number` 等错误属于阻断项。

## 最终打包

只有公式复核、逐页复核和 required gates 已闭环时，才把临时 run 收敛到公开目录：

```powershell
python scripts/package_agent_delivery.py thesis.docx `
  --run tmp\thesis_reviewed `
  --output output `
  --visual-manifest tmp\visual_review\visual_review.json `
  --template templates\latex\buaa\bhosc `
  --replace `
  --out tmp\package_report.json
```

PDF-only 输入还必须通过 `--editable-docx` 提供最佳努力的语义可编辑 DOCX。无法恢复语义结构时，
结果保持 `needs_review`；禁止把整页截图伪装成可编辑 Word。

打包器会：

1. flatten/inline 所有生成的 `data/*.tex`，保留 `\include` 的分页语义；
2. 把正文图片重写并复制到 `output/image/`；
3. 验证 run 中 `model.source`、`report.source_identity` 和 extraction source report 均与候选
   绝对路径、size 和 SHA256 一致；不允许覆盖身份后重新贴标；
4. 从扁平 `thesis.tex` 全新编译，并与已审 PDF 做逐页像素比较；
5. 验证每张视觉截图是其声明 PDF 页和 bbox 的真实 raster；
6. 规范化 `failure_queue.json`，最后写入 artifact manifest digest；
7. 只保留输出契约允许的文件。

## 输出契约

```text
output/
  thesis.docx
  thesis.pdf
  thesis.tex
  model.json
  report.md
  failure_queue.json
  image/
    visual_review.json
    page_*.png
    <final body figures>
```

`thesis.pdf` 是规范化主交付。对于 DOCX 输入，`thesis.docx` 是保留语义可编辑性的源文档副本；
它不代表 LaTeX PDF 的分页。过程日志、解包目录、单公式编译文件和缓存不得进入 `output/`。

## 独立验收

先在临时目录使用锁定模板从 `output/thesis.tex` 全新编译，确认页数一致，并对已审 PDF 做逐页
pixel comparison。随后运行两个 profile：

```powershell
python scripts/validate_agent_delivery.py `
  --candidate thesis.docx `
  --profile latex_pdf `
  --gate-board tmp\thesis_reviewed\harness\gate_board.json `
  --output output `
  --out tmp\delivery_latex_pdf.json

python scripts/validate_agent_delivery.py `
  --candidate thesis.docx `
  --profile agent_visual_review `
  --gate-board tmp\visual_gate_board.json `
  --output output `
  --out tmp\delivery_visual.json
```

只有两个报告均为 `pass`、`failures=[]`，且 G20-G28、V00-V02 所有 required gates 均为
`pass`，才能声明最终交付。

## 测试

```powershell
pytest tests -q
```

默认测试排除 `legacy_word` marker。坏样本 fixture 必须继续失败，不能通过放宽 validator 或修改
规则把错误变成通过。

## 仓库结构

```text
skills/normalizing-buaa-theses/  Agent 工作流、规则和 evals
buaa_thesis_kit/extract/         DOCX/PDF 结构化提取与 extraction Harness
buaa_thesis_kit/equations/       原生公式识别、转换、编译与验证
buaa_thesis_kit/latex/           BUAAthesis 渲染和版式 Harness
buaa_thesis_kit/harness/         独立 profiles、失败队列和交付验证
scripts/                         可选 CLI 工具
templates/latex/buaa/bhosc/      锁定的 BUAAthesis 运行依赖
tests/                           单元、回归、坏样本和 Skill 合约测试
```
