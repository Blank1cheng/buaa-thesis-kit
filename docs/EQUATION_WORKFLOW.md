# 公式工作流

公式处理由 `buaa_thesis_kit/equations/` 独立负责，主 renderer 只消费已通过门禁的 LaTeX。详细状态机、证据文件和命令参见 [EQUATION_NATIVE_PIPELINE.md](EQUATION_NATIVE_PIPELINE.md)。

## 固定顺序

1. DOCX OMML：解析 `m:oMath` / `m:oMathPara`。
2. DOCX MathType：提取 `Equation Native` 的 MTEF，调用 MathType SDK。
3. PDF 安全文本：仅在结构解析无歧义且 `requires_review=false` 时使用。
4. PDF/图片：按公式编号与页面几何定位，交给显式配置的图片公式识别器。

禁止从 OLE 文件名、上下文散文或损坏的 PDF 私有字符编码猜测公式。OCR 候选不能覆盖 OMML/MTEF。

## 写回规则

只有逐公式结果为 `converted` 时，主流程才会：

- 将 `kind` 改为 `latex`；
- 写入 `latex`；
- 将 `requires_review` 改为 `false`；
- 在 `body.tex` 中生成原生公式。

`candidate_needs_review`、`unsupported` 和 `failed` 保留原预览图及稳定 `H-EQ-xxx`。有 MathType 翻译警告的候选即使独立编译和视觉比对通过，也不能自动写回。

## 验证

```powershell
pytest tests/test_native_equation_pipeline.py tests/test_pdf_extract.py tests/test_buaa_latex_pipeline.py -q
python scripts/run_equation_pipeline.py "C:\Users\admin\Desktop\删减毕设.docx" --out output/equation_native_docx
python scripts/run_latex_pipeline.py "C:\Users\admin\Desktop\删减毕设.docx" --buaa-template-path templates/latex/buaa/bhosc --degree-type undergraduate --out output/latex_pipeline_native --sample-mode truncated
```

验收时必须确认 `body.tex` 不含 `oleObject*.bin`，`report.json` 的原生公式数量与逐公式证据一致，且所有未通过项仍在 `failure_queue.json`。
