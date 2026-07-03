# 北航本科论文 Agent Graph 修复框架设计

## 目标

搭建一个类似 LangGraph 的本地 Agent 执行框架，用于北航本科毕业设计（论文）格式规范化。系统必须同时满足两类要求：

1. **合规**：输出文档必须符合北航本科论文格式要求。
2. **保真**：尽量保留原 Word 文档的内容、结构、公式、图片、表格和局部版面。

第一组黄金样例的视觉标准来自 Word 正常导出的 PDF：

`C:/Users/admin/Desktop/崔润昊毕设打印版.pdf`

该 PDF 只作为版式和视觉基准，不作为正文内容来源。

## 最终输出结构

```text
output/
  thesis.docx
  thesis.pdf
  thesis.tex
  report.md
  image/
```

Graph 状态、渲染截图、参考 profile、日志、中间 DOCX/PDF 等过程文件默认写入临时目录并删除。只有显式使用 `--keep-work` 时，才保留在 `output/` 外部用于调试。

## 核心原则

整体策略是 **repair-first（先修复，不重建）**：

1. 复制源 Word/PDF 到工作区。
2. 检查原文档结构和格式缺陷。
3. 在 Word 副本上做最小必要修复。
4. 从修复后的 Word 导出 PDF。
5. 将导出的 PDF 与参考 profile 和规范规则做对照。
6. 只有失败项需要返工，避免无关重排。

当“保留原版式”和“满足规范”冲突时，优先选择能满足规范的最小编辑，同时保留正文顺序、图片、公式、表格和段落局部格式。

## Agent Graph

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

## 节点职责

- `ingest`：校验输入类型，复制源文件到工作区，初始化 graph 状态。
- `profile_reference`：渲染 `崔润昊毕设打印版.pdf` 的关键页，提取封面、任务书、正文页眉页码、书脊等参考 profile。
- `inspect_source`：判断源文档是否已有封面、书脊、任务书、声明、摘要、目录、正文、参考文献、附录、公式、图片和表格。
- `diagnose_compliance`：生成 `missing_cover`、`missing_spine`、`wrong_header`、`wrong_page_numbering`、`missing_task_book`、`metadata_conflict` 等类型化问题。
- `plan_minimal_fixes`：把问题转换为有序修复动作，优先局部 Word 编辑，不默认整篇重建。
- `apply_word_fixes`：在 Word 副本上插入或修复封面、书脊、前置页、分节符、页眉页脚、页码和样式，并保留正文。
- `export_pdf`：从修复后的 Word 导出 PDF，并拒绝无效 PDF。
- `visual_compare`：渲染输出 PDF，与参考 profile 做视觉特征对比。
- `decide`：根据 blocking/review/note 和重试次数决定返工或收口。
- `finalize_output`：只复制公开产物到 `output/`，写 `report.md`，删除默认过程文件。

## 书脊处理

书脊是强制合规对象，不是附加项。

Graph 必须检测、规划、修复和验证书脊：

- 源文档是否已有书脊页或书脊版式；
- 书脊字段是否完整：题名、学生姓名、院系/专业、年份；
- 是否能插入适合打印的 Word 书脊页；
- PDF 导出后书脊是否可见且字段正确；
- 报告中必须记录 `missing_spine`、`spine_metadata_missing` 或 `spine_visual_mismatch`。

## 第一阶段修复能力

- `.doc` 转 `.docx`；
- 复制 DOCX 作为可编辑基础；
- 插入/修复北航封面；
- 插入/修复书脊；
- 插入/修复任务书占位页；
- 规范正文页眉、页脚和页码；
- 保留正文段落、表格、图片和公式；
- 导出并校验 PDF；
- 生成辅助 TeX；
- 写入包含 graph findings 和视觉对照结果的报告。

## 验证标准

- graph 按节点顺序执行；
- 视觉检查失败时能回到修复规划；
- 缺少书脊时生成 `missing_spine`；
- 书脊修复动作必须排在最终 PDF 导出之前；
- graph 达到最大重试次数后必须失败退出；
- 最终输出目录不得包含过程文件；
- 用 `C:/Users/admin/Desktop/崔润昊毕设打印版.docx` 和 `C:/Users/admin/Desktop/崔润昊毕设打印版.pdf` 做黄金样例验收。
