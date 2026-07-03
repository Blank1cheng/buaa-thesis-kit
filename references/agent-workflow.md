# Agent 工作流

## 1. 接收与备份

先复制源 Word/PDF 到工作区，保留原文件不改。若同时有 Word 和 PDF，以 Word 为权威源；若只有 Word，则最终 PDF 从 Word 导出；若只有 PDF，先做文本、元数据和结构抽取，再套用统一 Word 模板生成可编辑 DOCX，并在报告中标记布局、公式和图表复核风险。

## 2. 结构识别

按规则加载器读取章节、元数据、图表、公式、参考文献规则。先识别封面、任务书、声明、摘要、目录、正文、参考文献，再处理样式。章节边界不确定时，不要猜测移动大段内容，改为人工复核。

## 3. 模板填充

使用 `templates/buaa_undergraduate_thesis_template.docx` 生成权威 Word 输出，使用 `templates/buaa_undergraduate_thesis_template.tex` 生成辅助 TeX。PDF 输入也必须生成可编辑 Word：封面、书脊、任务书和正文由模板文本渲染，不得把整页 PDF 截图嵌入最终 Word。图片和公式截图等资源统一放入 `output/image`，Word 内嵌资源，TeX 使用相对路径。

## 4. 校验与报告

生成 `output/report.md` 时记录每个关键元数据字段的置信度和证据；列出自动修改、警告、阻断项、人工复核项。报告中必须说明 Word 为权威源、PDF 从 Word 导出，避免用户误以为 TeX 是主输出。

## 5. 最终交付

只公开以下路径：`output/thesis.docx`、`output/thesis.pdf`、`output/thesis.tex`、`output/report.md`、`output/image/`。交付前检查 DOCX 可打开、PDF 来自最新 Word、TeX 无乱码、图片路径有效、报告无空白占位。
