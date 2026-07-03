# BUAA Thesis Kit

北航本科毕业设计（论文）格式规范化工具包。目标是把 `.doc`、`.docx` 或 `.pdf`
论文输入，经过可诊断、可回环的 Agent Graph 流水线，输出符合交付约束的 Word、PDF、
TeX 和图片目录。

## 核心策略

当前流水线采用 `repair-first`：

1. 优先复制并修复源 Word，尽量保留原文档版面、正文结构、图片、表格和公式对象。
2. 对 PDF 输入，只能先做文本/页面提取并生成可复核文档，报告中会标记布局复核风险。
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

## 使用方法

```powershell
python scripts/run_pipeline.py input.docx --out output
python scripts/run_pipeline.py input.doc --out output
python scripts/run_pipeline.py input.pdf --out output
python scripts/run_pipeline.py input.docx --out output --keep-work
```

`--keep-work` 只用于调试，会保留与 `output/` 相邻的过程目录；默认运行会删除过程文件。

## 报告状态

- `pass`：必需输出存在，且没有阻断项或人工复核项。
- `needs_review`：输出存在，但公式、图片、参考文献、元数据、PDF 版面或 OCR 仍需复核。
- `failed`：提取、Word 修复、TeX 生成或 PDF 导出出现阻断失败。

## 验证

```powershell
python -m pytest tests -q
python scripts/run_pipeline.py "D:\Work\研二下\Skill\论文\崔润昊毕设打印版.docx" --out output
python scripts/run_pipeline.py "C:\Users\admin\Desktop\崔润昊毕设打印版.pdf" --out output
```

真实样例中的公式和部分图片会被标记为 `needs_review`，这是预期行为：系统不会把不确定的
公式转换、图片位置、PDF 文本顺序或 OCR 缺口静默当作合格结果。
