# BUAA LaTeX Harness、任务书排版与产物清理设计

## 目标

在现有 LaTeX 主流程上完成一个可审计的小闭环：DOCX/PDF 输入仍以 `model.json` 为唯一内容源；本科输出使用仓库内固定的 BUAAthesis 模板；任务书技术要求和参考资料按黄金参考自然换行；harness 能捕获页面顺序、日期、目录颜色和任务书排版契约错误；清理所有可再生的早期过程产物，同时保留最新可验收 PDF、模型和报告。

本轮不修改公式识别结论：无法可信转换为原生 LaTeX 的 MathType 公式继续使用可读预览图，并在 G27 中保持 `needs_review`。

## 已确认根因

1. 抽取结果正确。`model.json` 已完整包含技术要求、五条任务书参考资料、正式参考文献和任务书日期范围。
2. `_assignment_text_lines()` 在 Python 中按固定显示宽度切断文本，随后每段碎片独立渲染，导致技术要求无法按实际字体和页面宽度自然换行。
3. 任务书参考资料使用 `1.12` 倍行距和 `1.8em` 悬挂缩进，与黄金参考的紧凑度和续行起点不一致。
4. `_com_info()` 将封面年月同时写入任务书开始、结束和答辩日期，覆盖了任务书中已经正确抽取的日期范围。
5. 本科主文件启用了 BUAAthesis 的 `color` 选项，使目录正文呈红色。
6. BUAAthesis 本科入口没有书脊页，当前页面序列为“封面 -> 任务书”，不满足既有验收要求。
7. G20-G27 只覆盖模板存在、编译、文本烟测和语义完整性，没有任务书/前置页布局契约，因此上述问题未进入 failure queue。
8. `templates/external/BUAAthesis` 是指向 `tmp/latex_refs/BHOSC_BUAAthesis` 的目录联接。清空 `tmp` 会破坏主流程。

## 方案

### 1. 固定模板来源

默认模板改为 `templates/latex/buaa/bhosc`。该目录已包含运行所需的 `buaathesis.cls`、GBT 7714 文件和四个 PDF 图形资源；这些文件与当前外部 clone 中对应文件的 SHA256 完全一致。

显式传入模板路径时仍允许使用外部 BUAAthesis clone。报告中的 `template_used` 必须记录解析后的真实路径。

### 2. 任务书自然排版

技术要求和工作内容保留源段落边界，不再把固定宽度切分结果写入主渲染宏。LaTeX 使用可换行下划线段落，在实际 `\textwidth`、字体和 CJK 断行规则下自然换行。Python 的显示宽度估算仅用于计算需要补齐的空白横线数，不得改变内容。

任务书排版契约：

- 技术要求、工作内容、主要参考资料固定为小四，不允许因内容较长缩小字号。
- 技术要求和主要参考资料使用 1.5 倍行距。
- 技术要求按源段落自然换行，每个可见行保持横线；短段落最后一行的横线补齐到右边界。
- 工作内容保留每条独立段落，并在内容不足时补齐模板空白横线。
- 任务书参考资料一条记录对应一个自然换行段落，不使用悬挂缩进，不在单词中硬切行。
- 正式参考文献继续使用 `2em` 悬挂缩进；不得和任务书参考资料共用样式。
- 内容超过单页容量时不缩小字号，G28 必须报 `taskbook_page_overflow`。

### 3. 日期与前置页

任务书开始和结束日期优先解析 `task_book.date_range`；答辩日期优先解析 `task_book.defense_date`。只有对应任务书字段不存在时才能回退到封面日期，并在报告中记录 fallback。

本科前置页顺序固定为：

1. 封面
2. 书脊
3. 任务书第一页
4. 任务书第二页
5. 本人声明
6. 中文摘要
7. 英文摘要
8. 目录
9. 正文

书脊使用独立的 `data/bachelor/spine.tex` 模板，从 `model.metadata.title_cn`、`student_name` 和固定校名填充竖排列。它不修改 BUAAthesis 封面实现。

本科最终主文件移除 `color` 选项，目录和正文链接均以黑色输出。

### 4. G28 布局契约

新增 `buaa_thesis_kit/latex/layout_validate.py`，独立负责 LaTeX/PDF 布局报告，避免继续扩大 `pipeline.py`。

G28 检查：

- 使用仓库模板时，模板路径不能落在 `tmp`。
- 本科主文件不得启用 `color` 选项。
- 技术要求宏必须使用自然段落，不能包含固定宽度切分后的碎片。
- 任务书参考资料必须是小四、1.5 倍行距且无悬挂缩进。
- 正式参考文献必须保留悬挂缩进。
- PDF 前九页的区域顺序符合前置页顺序。
- 任务书日期与 `model.task_book` 一致。
- 五条任务书参考资料均位于任务书第二页，条目编号不重复、不合并。
- 任务书第一页和第二页不得出现内容溢出到额外页面。

failure ID 由失败原因固定映射，不能依赖发现顺序。每项 failure 包含 `id`、`gate`、`reason`、`region`、`evidence_text`、`expected`、`suggested_fix` 和 `can_fix_now`。

G28 输出：

- `output/<run>/harness/taskbook_layout_report.json`
- `output/<run>/harness/frontmatter_sequence_report.json`
- `output/<run>/harness/taskbook_page_1.png`
- `output/<run>/harness/taskbook_page_2.png`

### 5. 清理策略

清理脚本只能操作当前仓库根目录中的 `generated`、`tmp` 和 `output`。任何解析后位于仓库之外的路径必须拒绝。

默认保留：

- `output/latex_pipeline/`
- `output/latex_pipeline_pdf/`
- `output/image/`
- `output/goal_acceptance.md`
- `output/goal_acceptance.json`
- `output/cleanup_report.json`
- `tests/fixtures/`、`templates/`、`rules/`、`references/` 和 `docs/`

默认删除：

- `generated/` 中所有早期 Word/公式/渲染探针
- `tmp/` 中所有可再生探针和外部模板 clone
- `output/` 中除保留白名单外的旧 spike、debug、probe、Word renderer、旧 harness 和空目录
- 已解除依赖后的 `templates/external/BUAAthesis` 目录联接

脚本先生成 dry-run 清单和预计字节数；执行后记录每个删除路径、实际释放字节数，以及保留的两个最终 PDF 的 SHA256。

## 验收标准

1. `pytest tests -q` 全部通过。
2. DOCX 输入 `C:/Users/admin/Desktop/删减毕设.docx` 端到端编译成功。
3. PDF 输入 `C:/Users/admin/Desktop/20375284-宋郭睿-毕业论文.pdf` 端到端编译成功。
4. DOCX 输出任务书技术要求为小四、1.5 倍行距、自然换行、无文字越界。
5. DOCX 输出任务书五条主要参考资料为小四、1.5 倍行距、无悬挂缩进、无单词硬切。
6. 正式参考文献继续使用悬挂缩进。
7. 任务书日期显示为 `2020 年 12 月 31 日至 2021 年 5 月 23 日`，答辩日期不从封面年月臆造。
8. 本科 PDF 包含书脊，前置页顺序正确，目录为黑色。
9. G28 为 `pass`；G27 仅允许保留已知公式预览 `needs_review`，不得新增 P0/P1 failure。
10. 清理后最新 DOCX/PDF 输出和报告仍可打开，模板解析不依赖 `tmp`，并报告实际释放空间。

## 非目标

- 不把 MathType MTEF 宣称为原生 LaTeX。
- 不修改摘要正文、正文内容、图片绑定算法或公式转换策略。
- 不重新实现 BUAAthesis 封面。
- 不删除当前仓库之外的任何文件。
