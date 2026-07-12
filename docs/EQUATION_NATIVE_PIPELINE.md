# 原生 LaTeX 公式子流程

该子流程独立于论文页面渲染，负责把公式从源文档定位、转换、验证后写回模型。页面 renderer 不负责猜测公式。

## 输入优先级

1. DOCX `m:oMath` / `m:oMathPara`：直接解析 OMML 结构。
2. DOCX MathType OLE：读取 `Equation Native`，去除 OLE native header 后调用本机 MathType SDK 翻译器。
3. PDF 可提取公式文本：只接受现有安全语法解析器能够无歧义解析的表达式。
4. PDF/图片公式区域：交给可插拔图像识别器生成候选；没有置信度和源区域证据时不得写回正文。

OCR 或图像识别永远不能覆盖可用的 OMML/MTEF 原生数据。

PDF 的图像公式定位使用右侧公式编号锚点（如 `(2-3)`），结合页面坐标、数学字体和垂直连通区域裁剪公式本体。每条记录保留页码、编号、`region_bbox` 和裁剪图 SHA256。定位成功不等于识别成功；未配置识别器时状态必须是 `unsupported`。

## 状态机

- `converted`：确定性转换成功，LaTeX 独立编译成功，源预览对比通过。
- `candidate_needs_review`：得到可编译候选，但源转换器有警告、视觉对比不足或识别置信度不足。
- `unsupported`：没有可用转换器或遇到未支持结构。
- `failed`：原生数据损坏、转换失败或候选 LaTeX 无法编译。

只有 `converted` 可以把 `requires_review` 改为 `false`。其他状态继续使用源预览图，并保留在失败队列。

## 逐公式证据

每个公式使用稳定 ID，并输出到 `output/equation_native/equations/<id>/`：

- `source.json`
- `source.omml` 或 `source.mtef`
- `source_preview.png`（若存在）
- `candidate.tex`
- `standalone.tex`
- `standalone.pdf` 和 `rendered.png`（编译成功时）
- `verification.json`
- `artifact_hashes.json`

总目录包含 `equation_manifest.json`、`failure_queue.json` 和 `report.json`。失败项使用稳定的 `H-EQ-xxx` ID。

## 验收门禁

1. 公式 ID、源段落/页码和 SHA256 可追溯。
2. LaTeX 不含文档级命令、外部文件读取或未配对花括号。
3. 每个候选在独立 XeLaTeX 文档中编译。
4. 有源预览时生成视觉对比指标；低于阈值进入复核，不放宽阈值。
5. `oleObject*.bin`、MTEF 二进制和 OCR 占位符不能出现在最终 `body.tex`。
6. 自动写回前必须同时满足确定性来源、编译通过和验证通过。

视觉比对是版面结构烟雾测试，比较长宽比、墨迹密度、粗网格和水平/垂直投影；它不替代 OMML/MTEF 的确定性语义来源检查。独立验证文档使用 `XITS Math`，避免 MathType Times 风格与 Computer Modern 字形差异造成系统性误报。

## 命令行

```powershell
python scripts/run_equation_pipeline.py output/latex_pipeline/model.json --out output/equation_native
python scripts/run_equation_pipeline.py "C:\path\thesis.docx" --out output/equation_native_docx
python scripts/run_equation_pipeline.py "C:\path\thesis.pdf" --out output/equation_native_pdf
```

DOCX 入口直接读取 OOXML、OMML 和 OLE，不先转 PDF。PDF 入口优先解析安全文本公式，无法无歧义解析时只输出公式区域图。

## 图片识别器协议

图片识别器通过显式 argv JSON 数组接入，不使用 shell：

```powershell
python scripts/run_equation_pipeline.py thesis.pdf `
  --out output/equation_native_pdf `
  --image-recognizer-command '["recognizer.exe","--input","{image}"]' `
  --recognizer-timeout 60
```

识别器 stdout 必须是一个 JSON 对象：

```json
{"latex":"E=mc^2","confidence":0.97,"engine":"local-math-ocr"}
```

图片识别结果无论置信度多高都先进入 `candidate_needs_review`，并继续执行安全检查、XeLaTeX 编译和源图比对。识别器路径、argv、退出码、耗时、stderr、引擎和置信度写入审计记录。

## 当前真实样例基线

- `删减毕设.docx`：定位 36 个 MathType 公式；32 个 `converted`，4 个因 MathType `translator_error (-14)` 保留为 `H-EQ-003`。
- `崔润昊毕设打印版.pdf`：定位 40 个编号公式区域；未配置图片识别器时 40 个均为 `unsupported`，不得声明原生 LaTeX 转换完成。
