# 公式处理规则

## Source priority

OMML 与 MTEF 同级并列第一，二者都先于 verified text；之后依次为 Agent visual、external OCR，且 external OCR is optional and not required.

1. 为每个公式建立由源 SHA、页码或部件、段落和序号派生的稳定 ID；修复和复核时保持该 ID。
2. 保存包含公式编号及少量上下文的裁剪，记录 bbox、原始结构、文本层和所有 LaTeX 候选；候选不得覆盖原始证据。
3. 若 OMML/MTEF 可解析，按结构转换；verified text 必须能绑定作者源或明确文本层。Agent visual 只生成或核对候选，不能凭模型置信度消除歧义。
4. 将每个候选放入最小 XeLaTeX 文档独立编译；编译成功只证明语法成立。
5. 对照裁剪逐符号检查字母与数字、上下标、重音、运算符、括号层级、分式、矩阵、字体和编号，并检查正文中的定义与后续引用。
6. 任一字符无法由独立证据消歧时，将同一公式记录为 `needs_review`，保留候选、裁剪、来源和缺失证据；不得把猜测写入 `thesis.tex`，并阻止总体状态成为 `pass`。`needs_review` must not be called final delivery，也不得正式交付论文。可以输出 `status=needs_review` 的完整复核包供人工基于同一稳定公式 ID 闭环，但报告必须称其为“复核包”而不是“交付”，且不得宣称通过或最终定稿。
7. 公式截图只能作为审计证据，公式图不得作为最终正文内容。
