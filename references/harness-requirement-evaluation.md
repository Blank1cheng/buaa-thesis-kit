# Harness 需求识别与评价体系

当前阶段先冻结 renderer 局部排版修改，把验收前移到需求识别、角色分类和输出污染检测。任何 agent 在继续改渲染前，都必须先跑 harness，并根据报告定位是模型抽取、模板继承、正文污染还是渲染几何问题。

## 角色分类

文本必须先被归入以下角色之一：

- `template_static_required`：官方模板固定文字，允许留在最终论文中，例如“单位代码”“本人声明”“Author:”。
- `template_instruction`：模板说明文字，禁止进入最终论文，例如“论文封面书脊”“四号黑体字”“（题目）”。
- `template_sample_value`：官方模板样例值，除非能证明来自用户源文档，否则禁止进入最终论文，例如“王小亮”、旧样例题目、样例参考文献。
- `user_fill_value`：从用户源文档抽取出的动态元数据，例如学号、姓名、题名。
- `source_body_content`：用户论文正文。
- `source_frontmatter_content`：用户论文摘要、任务书、声明等前置内容。
- `system_report_content`：只能写入 `output/report.md` 的系统诊断和复核信息。
- `debug_forbidden`：调试占位符、本地路径、中间文件名，禁止进入 `thesis.docx`。

角色定义在 `buaa_thesis_kit/harness/config/role_schema.yaml`，词表分布在 `config/template_sample_tokens.yaml`、`config/forbidden_tokens.yaml` 和 `config/region_rules.yaml`。新增规则时必须补对应测试，不能只在 renderer 里绕过。

## Harness 阶段

`scripts/run_harness.py` 默认按最小闭环执行：

1. `role_quiz`：验证角色分类词表和允许进入 thesis 的策略。
2. `model`：验证 thesis model 元数据、摘要区域和 forbidden token。
3. `output_text`：解包 DOCX，检查模板说明、样例值、debug token、摘要串区、目录污染和正文页眉/页码残留。

`template_inheritance` 和 `render` 暂时是显式可选阶段，分别通过 `--include-template-inheritance` 和 `--include-render` 开启。

默认遇到首个失败阶段即停止；调试时可用 `--continue-on-fail` 得到全阶段报告。

## 调试样本约束

`tests/fixtures/truncated_input.docx` 是截断样本，允许缺第 3/4/5 章和参考文献；这些缺失不能成为阻断项。截断模式仍必须检查前置页污染、debug 泄漏、本地路径泄漏和可编辑性。

`tests/fixtures/reference_good.docx` 是好样本，`validate_output_text.py` 必须通过。

`tests/fixtures/bad_outputs/thesis6.docx` 是当前坏输出回归样本，必须失败，并至少命中：

- `template_instructions_or_sample_leak`
- `cover_classification_split`
- `cn_abstract_contains_english_title`
- `toc_contains_declaration`
- `toc_contains_template_sample_reference`
- `body_contains_template_page_number_48`
- `title_line_break_bad`

## 报告要求

每次开发汇报必须说明：

- 失败的 harness 阶段或测试名。
- 修改了哪些规则文件和脚本。
- 是否改变 renderer 行为；若本轮只改 harness，必须明确 renderer 未改。
- 修改前后的 harness 报告差异。
- render diff 路径。
- 剩余 `failed` 或 `needs_review` 项。
