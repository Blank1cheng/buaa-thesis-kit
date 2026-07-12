# 公式处理规则

## Source priority

OMML 与 MTEF 同级并列第一，二者都先于 verified text；之后依次为 Agent visual、external OCR，且 external OCR is optional and not required.

1. 为每个公式建立由源 SHA、页码或部件、段落和序号派生的稳定 ID；修复和复核时保持该 ID。
2. 保存包含公式编号及少量上下文的裁剪，记录 bbox、原始结构、文本层和所有 LaTeX 候选；候选不得覆盖原始证据。
3. 若 DOCX 原生 OMML/MTEF 可解析，按结构转换；verified text 必须绑定作者源，PDF 文本层本身绝不构成 verified text。即使 PDF 文本候选可解析为分式、上下标、求和或矩阵，也保持 `needs_review`，不得生成伪原生 OMML 自动晋升。Agent visual 只生成或核对候选，不能凭模型置信度消除歧义。
4. 将每个候选放入最小 XeLaTeX 文档独立编译；编译成功只证明语法成立。
5. 对照裁剪逐符号检查字母与数字、上下标、重音、运算符、括号层级、分式、矩阵、字体和编号，并检查正文中的定义与后续引用。
6. 任一字符无法由独立证据消歧时，将同一公式记录为 `needs_review`，保留候选、裁剪、来源和缺失证据；不得把猜测写入 `thesis.tex`，并阻止总体状态成为 `pass`。`needs_review` must not be called final delivery，也不得正式交付论文。可以输出 `status=needs_review` 的完整复核包供人工基于同一稳定公式 ID 闭环，但报告必须称其为“复核包”而不是“交付”，且不得宣称通过或最终定稿。
7. 公式截图只能作为审计证据，公式图不得作为最终正文内容。

## Agent review ledger

原生转换仍无法自动闭环的公式，由 Agent 逐式查看 `source_preview.png` 与
`rendered.png`，并通过 `--equation-review <ledger.json>` 提交复核账本。账本必须：

1. 在根级记录 `source_candidate_path` 与 `source_sha256`，且必须等于本次输入的实际路径和 SHA；不得复用其他版本的账本。
2. 每条记录使用同一稳定公式 ID，记录 `reviewer: agent_visual`、非空 `evidence_text`，以及 `candidate.tex`、`source_preview.png`、`rendered.png` 的实际 SHA256。任一文件或 hash 不一致时保持 `needs_review`。
3. 若候选逐符号一致，明确记录批准结论。若 Agent 根据可见独立证据修正候选，必须同时记录 `correction_reason` 与 `corrected_latex_sha256`；不得只凭模型置信度改写。
4. Agent 改写 LaTeX 后，旧 `candidate.tex`/`rendered.png` 的 pass 立即失效；必须对修正值重新做安全检查、最小编译及来源裁剪比较，并写入 `corrected_candidate_sha256`、`corrected_rendered_sha256` 和更新后的 `artifact_hashes.json`。随后还须全文编译并检查正文渲染。只有对应公式通过后，才能从 active `failure_queue.json` 移除该公式的 H-ID。

示例执行入口：

```text
python scripts/run_latex_pipeline.py <input.docx-or.pdf> --buaa-template-path templates/latex/buaa/bhosc --degree-type <undergraduate-or-master> --out <temporary-run> --equation-review <ledger.json>
```
