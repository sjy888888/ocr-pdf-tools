# ocr-pdf-tools —— 扫描书数字化工具链

把扫描版 PDF（或带文字层的 PDF / Office 文档）变成干净的全文本 / 行级 JSONL / **听书友好 EPUB** 的一整套工具。

适用场景：手头有扫描版的书（无文字层），想 OCR 成电子书放进阅读器、或者转语音听书；书很长、页数多，需要断点续跑和并行加速。

```
扫描版 PDF
   │  pdf_render_pages.py   逐页渲染成灰度 PNG
   ▼
PNG 页图（p0001.png …）
   │  rapid_ocr_jsonl.py    RapidOCR → 行级 JSONL（带每行坐标，可断点续跑）
   │  ──或── ocr_pages.py / ocr_parallel.py   直接出全书 TXT（可分片并行）
   ▼
行级 JSONL ───── merge_ocr_full.py ────► 全书 TXT（校验缺页）
   │
   │  jsonl2epub5.py（配合 citations.py）
   │  目录书签 / 引文转章末注释 / 引号还原 / OCR 标点清理 / 听书友好排版
   ▼
听书友好 EPUB
```

## 快速开始

```bash
pip install rapidocr-onnxruntime pymupdf numpy opencv-python

# 1) 扫描版 PDF → 页图
python pdf_render_pages.py book.pdf pages/ 200

# 2) 页图 → 行级 JSONL（中途断了重跑同一命令即可续跑）
python rapid_ocr_jsonl.py pages/ book.jsonl

# 3) 行级 JSONL → EPUB（目录取 PDF 书签，引文转章末注释）
python jsonl2epub5.py book.jsonl book.epub "书名" "作者" book.pdf

# 如果 PDF 本身带文字层，不用 OCR，直接抽全文：
python deep_read.py book.pdf book.txt
```

## 工具详解

### 1. deep_read.py —— 无损提取文字层全文

带文字层的 PDF 和 Office 文档（docx/pptx/xlsx/odt 等）直接抽取原文，逐字无损，非 OCR、非概括。Office 文档通过 LibreOffice 转 PDF 后抽取（需要安装 LibreOffice，可用环境变量 `SOFFICE` 指定 `soffice.exe` 路径）。

```bash
python deep_read.py <文件路径> [输出.txt]
```

要点：只有扫描版（无文字层）的页会标注"无文字层"，此时才需要走 OCR。

### 2. pdf_render_pages.py —— PDF 逐页渲染为灰度 PNG

把扫描版 PDF 每一页渲染成 `p0001.png` 形式的灰度图片，供 OCR 使用。灰度体积约为彩色的 1/3，OCR 精度不受影响。已存在的页自动跳过（断点续跑）。

```bash
python pdf_render_pages.py <pdf路径> <输出目录> [dpi=200] [起始页=1] [结束页=0=到末尾]
```

### 3. ocr_pages.py —— RapidOCR 批量识别，输出带页码 TXT

用 RapidOCR（本地 ONNX 模型，离线可用）批量识别页图，按检测框坐标重排行序，输出带"【第 N 页】"标记的全文 TXT。**每页识别完立即写盘**，中断不丢结果；输出里已存在的页自动跳过，可断点续跑。

```bash
python ocr_pages.py <pages目录> <输出txt> [起始页] [结束页]
```

环境变量（可选）：`OCR_USE_CLS=1` 开启方向分类；`OCR_REC_BATCH` 识别批大小（默认16）；`OCR_THREADS` 线程数（默认-1）。

### 4. ocr_parallel.py —— 多进程并行 OCR

把全书按页分片，多个进程同时跑 `ocr_pages.py`，各自增量写盘，最后按页码合并成一本。Windows 下用宽字符参数传参，中文路径安全。已有分片文件自动跳过（断点续跑）。

```bash
python ocr_parallel.py <pages目录> <输出txt> [分片数=4]
```

### 5. rapid_ocr_jsonl.py —— RapidOCR → 行级 JSONL

与 `ocr_pages.py` 相同引擎，但输出为**带坐标的行级 JSONL**（与 EPUB 构建器同一数据格式），每行文字记录检测框坐标，供重排、去书眉、段落聚类使用。同样支持断点续跑。中文路径安全（用 `np.fromfile` 读取图片，兼容 Windows 中文路径）。

```bash
python rapid_ocr_jsonl.py <png目录> <out.jsonl> [每N页打一次日志=20]
```

### 6. merge_ocr_full.py —— 合并多份 OCR 输出并校验缺页

把多份 OCR 结果（支持"【第 N 页】"方括号格式和 `<!-- page N -->` HTML 注释格式）合并成统一全文，按页码升序，并报告哪些页缺失。适合分片并行后合并、或多来源结果归并。

```bash
python merge_ocr_full.py <输出txt> <输入1> [输入2 ...]
```

### 7. ocr_bench.py —— OCR 参数基准测试

同一批页图比较不同 RapidOCR 参数组合（是否开方向分类、批大小、线程数）的耗时，输出每页平均秒数，用于在本机挑选最快配置。

```bash
python ocr_bench.py <页图1> [页图2 ...]
```

### 8. citations.py —— 引文识别（供 jsonl2epub5 调用）

识别中文书刊常见引文格式，例如 `（《马克思恩格斯文集》第2卷，人民出版社2009年版，第591页）`、`参见《列宁选集》第2卷，人民出版社1995年版，第624页`，收集到章末"本章注释"，避免听书时被书注打断。被 `jsonl2epub5.py` 自动调用，一般无需单独运行。

### 9. jsonl2epub5.py —— 行级 JSONL → 听书友好 EPUB（核心构建器）

把带坐标的行级 JSONL 组装成 EPUB 3 电子书：

- **目录书签**：读取 PDF 的书签（两级：章/节），自动识别"第一章"中文数字或"第1章"阿拉伯数字章号
- **去书眉页码**：按"重复出现的顶部短行 + 章节名"规则剔除书眉，页脚页码一并清理
- **引文转章末注释**：调用 citations.py，把引文从正文挪到章末"本章注释"
- **引号标点修复**：OCR 常把中文引号识别成 ASCII 直引号，按奇偶配对还原“ ”‘ ’；清理 `，．`、连续句号等标点垃圾
- **段落重排**：按行坐标聚类成段（首行缩进、句末标点断段），正文两端对齐，听书朗读不断句

```bash
python jsonl2epub5.py <in.jsonl> <out.epub> <标题> <作者> <pdf路径>
```

## 行级 JSONL 格式说明

`rapid_ocr_jsonl.py` 与 `jsonl2epub5.py` 共用的数据格式：每行一个 JSON 对象，代表一页。

```json
{"page": 1, "w": 1654, "h": 2339, "engine": "rapid",
 "lines": [{"t": "正文文字", "x0": 82.0, "y0": 120.0, "x1": 900.0, "y1": 152.0}]}
```

| 字段 | 说明 |
|---|---|
| `page` | 页码，从 1 开始 |
| `w` / `h` | 页图宽 / 高（像素） |
| `engine` | OCR 引擎标识（如 `rapid`） |
| `lines[].t` | 行文字 |
| `lines[].x0/y0/x1/y1` | 该行检测框四角坐标（像素），供重排、去书眉使用 |

完整示例见 [examples/sample.jsonl](examples/sample.jsonl)。

## 特性一览

- **断点续跑**：渲染、OCR、合并所有长任务中断后重跑，自动跳过已完成页，不丢进度
- **并行加速**：`ocr_parallel.py` 分片多进程，Windows 中文路径安全
- **离线 OCR**：RapidOCR 本地 ONNX 推理，无需联网（首次运行自动下载模型）
- **听书友好**：引文转章末注释、书眉页码剔除、段落不断句，专为语音朗读优化

## 常见问题

**Q: Windows 控制台打印中文乱码？**
设置环境变量 `PYTHONUTF8=1` 再运行。

**Q: 提示找不到 LibreOffice？**
`deep_read.py` 处理 Office 格式需要 LibreOffice，用环境变量 `SOFFICE` 指定 `soffice.exe` 的完整路径。

**Q: 只适合中文书吗？**
以中文单栏书刊为主（简体横排效果最佳）；英文经测试也可用，但段落/标点修复逻辑偏中文。

## 许可证

MIT License，详见 [LICENSE](LICENSE)。
