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
- `thesis.tex` 必须 flatten/inline generated TeX fragments 和 bibliography 数据，或使用无需额外 `.bib` 文件的参考文献内容；最终文件不得继续依赖 `\include{data/...}`、`\input{data/...}` 或未交付的 generated TeX fragments。所有最终正文图片必须位于 `output/image/`。报告记录可复现编译命令，以及输入、TeX、正文图片、BUAAthesis 依赖和 PDF 的 hashes。
- `output/thesis.docx` 始终是必需交付。DOCX 输入必须保留文本、表格、图片和公式的语义可编辑结构。PDF-only 输入无法可靠恢复原结构时，仍输出最佳努力的语义可编辑 DOCX，并在 `report.md` 与 `failure_queue.json` 明确标记 `needs_review` 和缺失清单；严禁用整页截图伪造正文或前置页，也不得宣称 `pass`。
- `model.json` 保存证据模型；`model.json source` 必须记录与实际候选完全一致的 `candidate_path`、`source_sha256`、`source_size` 和 `source_type`。pipeline report 与 extraction source report 必须记录同一身份，打包器只能验证，禁止用命令行候选覆盖旧 run 身份。`report.md` 保存输入/TeX/PDF SHA、能力、编译记录、gate 结果和截图索引；`failure_queue.json` 保存未闭环 H-ID。
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

## Final packaging and validation

Agent 完成公式复核、逐页视觉检查和 Harness gates 后，使用确定性打包器把临时 run
收敛到平面目录。`--out` 必须位于公开 `output/` 之外；打包器只复制已有结论，不得把
`needs_review` 或 `failed` 改为 `pass`。

```text
python scripts/package_agent_delivery.py <candidate> --run <temporary-run> --output output --visual-manifest <review-dir>/visual_review.json --template templates/latex/buaa/bhosc --replace --out <temporary-dir>/package_report.json
```

打包器在原子替换公开目录前，先在临时目录放入锁定的 BUAAthesis 依赖、扁平 `thesis.tex` 与 `image/`，执行一次 fresh compile，比较 page count 和逐页 pixel comparison，并以已审 pipeline PDF 为比较对象；页数或任一页像素不一致时中止打包。`--replace` 只能删除名为 `output`、仅含交付契约项且不与 source/run/template/manifest 路径重叠的目录。

最后分别运行 LaTeX/PDF profile 与 Agent visual profile。示例：

```text
python scripts/validate_agent_delivery.py --candidate <candidate> --profile latex_pdf --gate-board <temporary-run>/harness/gate_board.json --output output --out <temporary-dir>/delivery_latex_pdf.json
python scripts/validate_agent_delivery.py --candidate <candidate> --profile agent_visual_review --gate-board <temporary-dir>/visual_gate_board.json --output output --out <temporary-dir>/delivery_visual.json
```

只有两个验证报告均为 `pass`、`failures` 为空，且实际候选 SHA 与 `model.json source`、
`report.md`、视觉清单完全一致时，才可称为最终交付。
