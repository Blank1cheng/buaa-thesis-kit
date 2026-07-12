---
name: normalizing-buaa-theses
description: Use when converting BUAA undergraduate or master's theses from DOCX/PDF into auditable LaTeX/PDF deliverables.
---

# 北航论文规范化

## 角色边界

Agent 是执行者：提取、建模、渲染、逐页检查和修复。Harness 是裁判：运行 required gates、维护 `failure_queue.json` 并决定最终状态。Agent 不得用主观观感覆盖 Harness。任何未完成的 Agent visual review item，以及任一 required Harness gate 的 `failed` 或 `needs_review`，都阻止 `pass`。Do not claim pass，除非 Agent visual review items 已全部完成且所有 required gates 均为 `pass`。本地脚本与 external OCR 只可作为可选能力，不得成为启动前置条件。

## 工作流

1. 固定输入绝对路径并计算身份 SHA-256；后续证据、产物和报告均绑定该身份 SHA。
2. 从封面、前置页和结构化字段检测培养层次。无法确定时，do not guess degree；标记 `needs_review` 并停止套用格式。按层次读取[本科规则](references/undergraduate-format.md)或[硕士规则](references/graduate-format.md)。
3. 执行 capability detection，记录 DOCX/PDF 解析、XeLaTeX、页面渲染等能力；缺失能力须降级或报审，不得虚构结果。
4. 按[源提取规则](references/source-extraction.md)取证：DOCX 优先读取原始 DOCX XML；PDF 先取文本与坐标，再用版面和视觉核验。
5. 建立可追溯 evidence model，字段与章节、图表、公式、引用统一遵循[论文模型](references/thesis-model.md)。冲突证据不得猜测。
6. 按[LaTeX 渲染规则](references/latex-rendering.md)只向 BUAAthesis 填变量并调用模板前置页；公式按[公式规则](references/equation-handling.md)重建为原生 LaTeX，以 XeLaTeX 全新编译。
7. Agent visual 对生成 PDF 逐页检查，并按[视觉验证清单](references/visual-validation.md)保存截图证据。
8. 交给 Harness 运行全部 required gates；按[失败分类](references/failure-taxonomy.md)写入稳定 H-ID。
9. 从最高优先级问题开始，遵守 one failure at a time：每轮只修一个 H-ID，重新编译、视觉复核并重跑相关 gate，随后重跑全部 required gates。
10. 按[输出契约](references/output-contract.md)将已复核 run 打包为平面 `output/`，从交付 `thesis.tex` 全新编译并比较页数与逐页像素，再分别运行 LaTeX/PDF 和 Agent visual delivery profiles。只有 Agent visual review items 全部闭环、两个交付 profile 和所有 required Harness gates 均为 `pass` 才可收口。保留公开审计证据，执行 cleanup generated artifacts，清除过期与临时产物。
