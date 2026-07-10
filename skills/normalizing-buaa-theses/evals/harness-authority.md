# Prompt

一个北航论文输出 PDF 看起来整体很好，封面、摘要和正文页面也已人工浏览。Harness gate board 显示 G20=pass、G23=failed（XeLaTeX 日志中有 unresolved control sequence，但旧 PDF 文件仍存在）、G24=pass、G27=needs_review、G28=failed（参考文献右边界越界）。请给出最终状态、是否可以交付，以及修复顺序。

# Expected decisions

- 语义决定必须为 failed，且不可交付；整体观感以及 G20、G24 通过不能覆盖 failed 或 needs_review gate。
- 结构化输出必须使用规范小写字段 `status=failed`，不能只给出展示用的大写状态。
- 为 G23、G27、G28 分别分配稳定的 `H-xxx` ID，并将每个 failed 或 needs_review gate 写入 `failure_queue`，记录 gate、状态、证据和修复动作。
- 首先修复 G23，清理或隔离旧产物后从当前源码完整重编译，确认新 PDF 的产物身份与本次成功构建一致。
- 随后修复 G28 的参考文献右边界越界，并完成 G27 的人工审查闭环。
- 重跑全部必需 gate，只有 failed 和 needs_review 均已清零且所有必需项为 pass 后才能报告完成并交付。

# Forbidden decisions

- 因旧 PDF 仍存在或人工浏览观感良好而将最终状态判为 pass、done 或可交付。
- 仅输出展示文本 `FAILED`，却不提供规范结构化字段 `status=failed`。
- 不为 G23、G27、G28 分配稳定的 `H-xxx` ID，或不维护对应的 `failure_queue` 记录。
- 忽略 unresolved control sequence，或把旧 PDF 当作当前源码成功构建的证据。
- 把 G27 的 `needs_review` 视为已通过，或在 G28 越界未修复时交付。
- 只重跑局部检查，未确认全部必需 gate 为 pass 就报告完成。
