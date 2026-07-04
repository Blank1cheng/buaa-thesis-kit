# 官方模板原位编辑工作流

## 目标

`附件1-北航本科论文模板.doc` 是唯一版式来源。主流程必须先转换并 instrument 官方模板，然后每次复制 instrumented 模板到 `output/thesis.docx`，再在这个副本内部替换内容。不得把官方模板拆成 cover/spine/task/abstract/body fragments 后重新拼接。

## 阶段 1：准备官方模板

```powershell
python scripts/prepare_official_template.py "D:\Work\研二下\Skill\格式要求\附件1-北航本科论文模板.doc" --out templates\official\buaa_undergraduate_template.docx --render-check-dir output\template_render_check
python scripts/instrument_official_template.py --template templates\official\buaa_undergraduate_template.docx --out templates\official\buaa_undergraduate_template_instrumented.docx
python scripts/extract_style_map.py --template templates\official\buaa_undergraduate_template.docx --out templates\official\style_map.json
```

验收：

- `templates/official/buaa_undergraduate_template.docx` 是有效 DOCX。
- `templates/official/buaa_undergraduate_template_instrumented.docx` 与官方模板包结构一致，只修改 `word/document.xml` 中的可替换标记。
- `styles.xml`、`numbering.xml`、header/footer、section breaks、TOC field、page number fields、media、shapes、textboxes 保留。
- `instrument_manifest.json` 记录插入的 placeholder，且 `fragment_assembly=false`。

## 阶段 2：主装配契约

主装配器是 `buaa_thesis_kit/assemble_in_place.py`：

```text
copy templates/official/buaa_undergraduate_template_instrumented.docx -> output/thesis.docx
replace scalar placeholders
replace multi-paragraph placeholders
remove official sample body between {{BODY_START}} and {{BODY_END}}
insert thesis model body blocks using official style ids
preserve package parts other than word/document.xml
```

正文插入只使用官方模板已有 style id：chapter、section、subsection、body、figure caption、table caption、reference。不要在主流程里设置字体、字号、行距、页边距、页眉页脚或页码。

## 阶段 3：继承性验证

每次输出必须生成：

```powershell
python scripts/validate_template_inheritance.py --base templates\official\buaa_undergraduate_template_instrumented.docx --candidate output\thesis.docx --out output\template_inheritance_report.json --word-com-finalized
```

`status=pass` 至少要求：

- `created_by_copying_base=true`
- `styles_xml_changed=false`
- `numbering_xml_changed=false`
- `toc_field_exists=true`
- `page_number_fields_exist=true`
- `header_footer_as_body_text=false`
- `frontmatter_generated_by_add_paragraph=false`
- `fragment_merge_used=false`

## 禁止项

最终 `thesis.docx` 不得出现：

```text
[Figure inserted]
[Figure requires review]
D:\
.worktrees
output_work_
本页由规范化流水线
需人工复核
任务内容、进度安排和指导记录请以学校原始任务书为准
本人郑重声明
指导教师签名
References
MERGEFORMAT
公式章
下一章
```

这些信息只能进入 `output/report.md` 或证据账本，不能混入 Word 正文。

## 调试工具边界

`scripts/extract_render_fragments.py` 可以保留为诊断工具，用来观察官方模板页块和 anchor，但它不能被主流水线调用，也不能作为最终装配方式。若 `template_inheritance_report.json` 显示 `fragment_merge_used=true` 或 `frontmatter_generated_by_add_paragraph=true`，本轮输出直接判定失败。
