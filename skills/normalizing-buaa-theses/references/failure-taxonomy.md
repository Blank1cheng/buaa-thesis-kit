# Harness 失败分类

## 状态

- `failed`：required gate 有可证实的错误，或构建本身失败。
- `needs_review`：现有证据不足以判定正确，必须人工或独立证据闭环。
- `pass`：该 gate 的全部检查与证据均满足要求。

总体状态按最严重 required gate 决定：任一 `failed` 则总体 `failed`；没有 `failed` 但存在 `needs_review` 则总体 `needs_review`；只有全部 required gates 为 `pass` 才能总体 `pass`。required gate 不可被其他 `pass`、旧产物或整体观感覆盖。

## 稳定 H-ID

每个未闭环问题写入 `failure_queue.json`。ID 统一采用 `H-<gate>-<semantic-key>`；semantic key 描述问题语义并保持稳定，不依赖 evidence 或问题出现顺序。需要转码时使用无损编码。示例：`H-G28-COVER-REVIEW`。记录必须含：

```yaml
id: H-G28-COVER-REVIEW
gate: required-gate-id
status: failed|needs_review|resolved
reason: concise-machine-readable-reason
region: source-part-page-paragraph-or-bbox
evidence:
  paths: [source-or-screenshot-path]
  page: integer-or-null
  bbox: [x0, y0, x1, y1]
  sha256: source-or-artifact-sha256-or-null
evidence_text: concise-observation-and-evidence-summary
expected: required-result
suggested_fix: one-actionable-change
can_fix_now: true-or-false
```

`evidence` 与 `evidence_text` 必须同时存在，不能二选一。结构化 `evidence` 明确包含 `paths`、`page`、`bbox` 和 `sha256`：用 `paths` 定位源文件、截图或裁剪，用 `page` 和 `bbox` 锁定区域，并用 `sha256` 绑定证据版本；`evidence_text` 提供简短事实摘要，不替代结构化定位。

active `failure_queue.json` 只包含状态为 `failed` 或 `needs_review` 的未闭环项。每轮只处理一个 H-ID；修复后追加新证据并重跑其 gate，将同一 ID 标为 `resolved`，再把完整记录迁移或记录到 `report.md` 的 resolved history，并从 active queue 移除。已分配的 ID 永不复用。关闭所有问题后仍须重跑全部 required gates，Harness 才能重新裁决总体状态。

## Semantic H-ID

Every H-ID uses a stable semantic key, for example
`H-G28-COVER-REVIEW`. An H-ID must not depend on evidence or occurrence order;
changing diagnostic evidence must not change the issue identity. A generated ID
may use a lossless encoding of its semantic key when needed. After resolution,
the resolved history retains the same ID that appeared in the active queue.
