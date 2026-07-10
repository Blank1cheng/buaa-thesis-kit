# 可审计论文模型

使用 UTF-8 JSON 保存唯一规范模型。模型根部必须含 `source`、`degree`、`fields`、`chapters`、`figures`、`tables`、`equations`、`citations` 和 `references`。

## 字段证据

每个字段均使用同一记录结构：

```yaml
value: string-or-null
source_path: absolute-source-path
source_sha256: lowercase-sha256
part: docx-part-or-pdf
page: integer-or-null
paragraph: stable-paragraph-id-or-null
bbox: [x0, y0, x1, y1]
method: docx_xml|omml|mtef|pdf_text|verified_text|agent_visual|external_ocr|user_confirmed
confidence: 0.0-to-1.0
review: pass|needs_review
```

`bbox` 使用源页面坐标；非页面证据可为 `null`。`confidence` 只表示提取把握，不能把 `needs_review` 自动提升为 `pass`。`external_ocr` 只能产生候选，必须保持 `review: needs_review`，直至由更高优先级独立证据完成复核。用户明确提供的值仍需记录消息或附件的来源标识。

## 内容结构

- `chapters[]`：`id`、`title`、`level`、`order`、`source_field_ids`、`paragraph_ids`。
- `figures[]`：`id`、`chapter_id`、`caption`、`asset_path`、`page`、`bbox`、`source_field_ids`。
- `tables[]`：`id`、`chapter_id`、`caption`、`cells`、`page`、`bbox`、`source_field_ids`。
- `equations[]`：稳定 `id`、`number`、`latex`、`candidates`、`page`、`paragraph`、`bbox`、`method`、`confidence`、`review`。
- `citations[]`：`id`、`key`、`raw_text`、`chapter_id`、`paragraph_id`、`target_reference_ids`。
- `references[]`：`id`、`key`、作者、题名、出版字段、`raw_text`、`cited_by`、证据字段。

所有交叉引用只使用稳定 ID；重排章节不得改变对象身份。
