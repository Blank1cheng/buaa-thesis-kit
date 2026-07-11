# 输出契约

`output` 保持平面结构，必须且只允许以下交付路径；`image` 是唯一子目录：

```text
output/thesis.docx
output/thesis.pdf
output/thesis.tex
output/model.json
output/report.md
output/failure_queue.json
output/image/
```

- `thesis.pdf` 是主交付。`report.md` 必须锁定 BUAAthesis 的版本或 commit、XeLaTeX 引擎及发行版版本、所需 fonts 及其可核验标识；不得声称一个未安装这些依赖的空白环境可以自包含复现。
- `thesis.tex` 必须内联 bibliography 数据，或使用无需额外 `.bib` 文件的参考文献内容；所有最终正文图片必须位于 `output/image/`。报告记录可复现编译命令，以及输入、TeX、正文图片、BUAAthesis 依赖和 PDF 的 hashes。
- `output/thesis.docx` 始终是必需交付。DOCX 输入必须保留文本、表格、图片和公式的语义可编辑结构。PDF-only 输入无法可靠恢复原结构时，仍输出最佳努力的语义可编辑 DOCX，并在 `report.md` 与 `failure_queue.json` 明确标记 `needs_review` 和缺失清单；严禁用整页截图伪造正文或前置页，也不得宣称 `pass`。
- `model.json` 保存证据模型；`report.md` 保存输入/TeX/PDF SHA、能力、编译记录、gate 结果和截图索引；`failure_queue.json` 保存未闭环 H-ID。
- `output/image/` 同时存放 `thesis.tex` 引用的最终正文图片资产，以及审计所需的页面截图与区域裁剪；它是 `output` 下唯一允许的子目录。最终正文图片是可复现交付资产，不是过程文件，必须纳入 TeX 依赖与 hash 索引。使用文件名前缀或 `report.md` 索引明确区分正文资产与审计证据。
- 解包目录、OCR 中间件、辅助文件、单式编译文件和试渲染均写入临时目录；交付前清理这些过程文件及过期产物，不得在 `output` 增加其他子目录。

## Artifact identity

The `report.md` Artifact identity section contains exactly these values:

- `source_candidate_path`
- `source_sha256`
- `source_size`
- `artifact_manifest_sha256`

The artifact manifest digest covers every public file, including all files in
`output/image/`, in sorted relative-path order. It must exclude report.md to avoid a circular digest cycle. The delivery root, required artifacts, `image`
directory, and image files must be regular local paths; symlink and junction
artifacts are forbidden.
