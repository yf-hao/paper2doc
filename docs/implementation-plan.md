# paper2doc 实施方案

## 1. 项目目标

创建一个将 PDF 论文转换为 DOCX 的程序，满足以下要求：

- 保留 PDF 中的正文、图片和图片说明。
- 支持单栏和双栏论文。
- 双栏 PDF 按正常阅读顺序读取，不能将左右栏按行交错。
- 将英文正文翻译为中文。
- 每个英文段落和对应的中文翻译成对出现，英文在上、中文在下。
- 根据图片在 PDF 中的实际页面位置和栏位置，将图片关联到相应段落。
- 识别文字型 PDF 表格，翻译单元格并在 DOCX 中保留原生表格结构；无法可靠
  恢复网格时保留表格区域图片。
- 图片放在所属英文段落及中文翻译之后。
- 使用 Word 原生的首行缩进和段落间距，不使用空格或空白段落模拟格式。
- DOCX 的排版参考中文核心期刊风格，并允许通过目标期刊模板覆盖默认格式。
- 翻译使用 OpenAI 兼容 API，不绑定具体供应商。

项目优先保证内容顺序、双语对应关系和图片不丢失，不以 PDF 与 DOCX 像素级一致为目标。

## 2. 目标输出

每个正文内容单元的顺序为：

```text
英文段落
中文翻译段落
图片
英文图注
中文图注
```

没有图片时：

```text
英文段落
中文翻译段落
```

表格内容单元的顺序为：

```text
表格标题（英文）
表格标题（中文）
英文原生表格
中文原生表格
```

PyMuPDF 的 `find_tables()` 可用时优先使用其单元格边界；否则实现使用页面
绘图中的横线和文本块坐标推断行列，特别覆盖无竖线但有水平分隔线的表格。
表格单元格使用 `table:<id>:r<row>:c<col>` 标记参与批量翻译，空单元格不生成
翻译请求但仍保留在两个 Word 网格中。若只能确定表格区域而不能恢复可靠网格，
则插入原始区域截图作为安全回退。

示例：

```text
    The proposed method improves the accuracy.
    所提出的方法提高了准确率。

    [图片]
    Fig. 6. Architecture of the proposed model.
    图 6：所提出模型的架构。
```

英文使用普通 DOCX 段落，中文翻译放入独立的一行一列表格单元格中。不能通过
在文本中拼接 `\n\n`、空格或制表符模拟表格边界、缩进和间距。

## 3. 技术栈与 Conda 环境

建议使用 Python 实现。

### 3.1 创建环境

```bash
conda create -n paper2doc \
  --override-channels \
  -c https://repo.anaconda.com/pkgs/main \
  python=3.11 pip -y
conda activate paper2doc
```

### 3.2 安装依赖

```bash
conda activate paper2doc
python -m pip install -e '.[ocr]'
```

macOS 还需要安装 Tesseract 可执行程序：

```bash
brew install tesseract
```

依赖用途：

| 依赖 | 用途 |
|---|---|
| PyMuPDF | 读取 PDF，提取文本块、图片块和坐标 |
| python-docx | 创建和格式化 DOCX |
| Pillow | 图片读取、转换和尺寸处理 |
| pytesseract | 调用 Tesseract OCR |
| OCRmyPDF | 为扫描版 PDF 添加 OCR 文本层 |
| openai | 调用 OpenAI 兼容格式的翻译 API |
| python-dotenv | 自动读取 `.env` 配置 |

项目使用 `pyproject.toml` 作为依赖和 CLI 注册的唯一来源；`.[ocr]` 会同时安装扫描版 PDF 所需的可选依赖，不需要手动逐个安装 Python 包。

## 4. OpenAI 兼容翻译配置

翻译通过 `base_url` 适配 OpenAI 官方 API、本地推理服务或其他兼容 Chat Completions 接口的服务，不在代码中绑定供应商。

### 4.1 配置项

| 配置项 | 作用 | 是否必需 |
|---|---|---|
| `OPENAI_API_KEY` | API 密钥；本地服务无鉴权时使用服务要求的占位值 | 是 |
| `OPENAI_BASE_URL` | OpenAI 兼容 API 根地址，通常需要包含 `/v1` | 否，默认官方地址 |
| `OPENAI_MODEL` | 翻译模型名称，必须与服务端可用模型一致 | 是 |

`.env.local` 是模板，使用时复制为项目根目录的 `.env`：

```bash
cp .env.local .env
```

`OPENAI_BASE_URL` 也可以配置为：

```text
http://127.0.0.1:8000/v1
https://example.com/v1
```

### 4.2 官方 API

将 `.env.local` 复制为 `.env` 后，填写以下配置：

```dotenv
OPENAI_API_KEY=真实密钥
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=指定模型名称
```

### 4.3 本地兼容服务

```dotenv
OPENAI_API_KEY=local
OPENAI_BASE_URL=http://127.0.0.1:8000/v1
OPENAI_MODEL=本地模型名称
```

即使本地服务不校验密钥，客户端通常仍要求传递 `api_key` 字段。

### 4.4 第三方兼容服务

```dotenv
OPENAI_API_KEY=第三方密钥
OPENAI_BASE_URL=https://第三方域名/v1
OPENAI_MODEL=第三方模型名称
```

### 4.5 保存个人配置

程序启动时会自动从当前工作目录及其父目录查找 `.env`，不需要手动执行 `export` 或 `source`。`.env.local` 仅作为模板，建议复制为不提交到 Git 的 `.env`：

```bash
cp .env.local .env
```

`.env` 不能提交到 Git，也不能写入日志或生成的 DOCX；`.env.local` 只保存不含真实密钥的模板。

配置优先级建议为：

```text
命令行参数 > .env > 已存在的环境变量 > 默认值
```

使用 `load_dotenv(..., override=True)` 读取 `.env`，因此文件中已定义的配置会覆盖已有的系统环境变量；文件中未定义的配置仍可从系统环境变量读取。API 密钥不设置默认值；缺少 `OPENAI_API_KEY` 或 `OPENAI_MODEL` 时应直接报错。

### 4.6 翻译客户端

翻译接口独立于 PDF 和 DOCX 逻辑，具体实现使用 OpenAI Python SDK：

```python
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI


for parent in (Path.cwd(), *Path.cwd().parents):
    dotenv_path = parent / ".env"
    if dotenv_path.is_file():
        load_dotenv(dotenv_path, override=True)
        break


class Translator:
    def __init__(self):
        api_key = os.environ["OPENAI_API_KEY"]
        base_url = os.environ.get("OPENAI_BASE_URL")
        self.model = os.environ["OPENAI_MODEL"]

        client_options = {"api_key": api_key}
        if base_url:
            client_options["base_url"] = base_url

        self.client = OpenAI(**client_options)

    def translate(self, text: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是学术论文翻译助手。将英文准确翻译为中文，"
                        "保留公式、变量名、引用编号和专业术语。"
                        "只返回中文译文，不添加解释。"
                    ),
                },
                {"role": "user", "content": text},
            ],
        )

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("Translation API returned an empty response")

        return content.strip()
```

翻译要求：

- 以段落为单位翻译，保证英文和中文一一对应。
- 专业术语前后一致。
- 公式、变量名和引用编号不被错误翻译。
- `Fig. 6` 等图号可以翻译为中文表达，但不能改变图片位置。
- 翻译失败时抛出明确错误，不生成空的中文段落。
- 有限次数重试后仍失败时，应保留原始段落并记录错误。

## 5. 总体处理流程

```text
输入 PDF
    ↓
判断是否为文字型 PDF
    ↓
必要时执行 OCR
    ↓
提取文字块、图片块、表格块、图注和坐标
    ↓
识别表格并从普通文字块中排除其单元格
    ↓
识别单栏、双栏和跨栏区域
    ↓
合并文字行为正文段落
    ↓
按照页面位置关联图片和段落
    ↓
逐个英文段落翻译为中文
    ↓
按“英文段落 → 中文段落 → 图片 → 图注”生成内容序列
    ↓
生成 DOCX
```

## 6. PDF 内容提取

使用 PyMuPDF 的字典格式提取页面内容：

```python
import pymupdf as fitz

document = fitz.open("input.pdf")

for page_number, page in enumerate(document):
    page_data = page.get_text("dict")

    for block in page_data["blocks"]:
        if block["type"] == 0:
            # 文本块，包含 lines、spans 和 bbox
            pass
        elif block["type"] == 1:
            # 图片块，包含 bbox 和图片数据
            pass
```

每个元素至少保留：

```python
{
    "page": 1,
    "type": "paragraph",
    "bbox": [72, 140, 520, 190],
    "column": "left",
    "text": "The proposed method improves the accuracy."
}
```

表格块额外保留页面号、整体 `bbox`、标题、行列数，以及每个单元格的
`row`、`column`、`bbox`、`row_span` 和 `col_span`。`find_tables()` 不可用时，
从 `get_drawings()` 的横线和文本块起始位置推断无竖线表格；若推断不可靠则
保留表格区域截图。

`bbox` 的格式为：

```text
[x0, y0, x1, y1]
```

## 7. 双栏布局处理

### 7.1 阅读顺序

不能把双栏页面的所有元素放在一起后直接按 `y` 坐标排序，否则会变成：

```text
左栏第 1 行
右栏第 1 行
左栏第 2 行
右栏第 2 行
```

正常顺序通常是：

```text
左栏全部内容
右栏全部内容
```

### 7.2 列识别

页面元素分为：

- `left`：左栏元素
- `right`：右栏元素
- `full`：跨两栏的全宽元素

全宽元素包括标题、作者、摘要、跨栏图片和跨栏表格。

基础判断：

```python
def classify_column(bbox, page_width):
    x0, _, x1, _ = bbox
    middle_x = page_width / 2
    width = x1 - x0

    if x0 < middle_x < x1 and width > page_width * 0.6:
        return "full"
    if x1 <= middle_x:
        return "left"
    return "right"
```

### 7.3 页面区域排序

如果页面中间出现跨栏图片或表格，不能把所有全宽元素放在页面顶部。应根据全宽元素的纵坐标切分区域：

```text
区域 1：页面顶部跨栏内容
区域 2：左栏内容 → 右栏内容
区域 3：跨栏图片及图注
区域 4：左栏内容 → 右栏内容
```

每个区域内部：

1. 处理区域顶部的全宽元素。
2. 左栏按从上到下排序。
3. 右栏按从上到下排序。
4. 处理下一个区域。

## 8. 段落识别

PDF 返回的文字通常是行或文字块，需要合并为正文段落。合并时考虑：

- 相邻行的垂直距离。
- 字体大小和行高。
- 所属页面和栏。
- 左侧起始位置是否一致。
- 是否出现新的标题或章节。
- 行尾连字符是否需要与下一行合并。

段落合并必须在栏识别之后进行，不能跨栏合并文字。

```python
{
    "id": 12,
    "type": "paragraph",
    "page": 2,
    "column": "left",
    "bbox": [72, 220, 265, 285],
    "text": "The proposed method improves the accuracy."
}
```

## 9. 图片与段落的关联规则

图片归属以 PDF 中的**实际版面位置**为准，不根据正文中的 `Fig. 6` 或 `Figure 6` 引用主动移动图片。

关联优先级：

```text
同一页面、同一栏中图片上方最近的段落
    >
同一页面中距离最近的段落
    >
当前版面区域中最近的段落
```

基本规则：

1. 图片和候选段落优先位于同一页面。
2. 普通图片和段落优先位于同一栏。
3. 段落应位于图片上方。
4. 在满足条件的段落中，选择与图片垂直距离最近的段落。
5. 跨两栏图片视为当前区域的全宽元素。
6. 图片位于栏顶部且上方没有段落时，使用同栏中距离最近的下方段落或当前区域第一段落。

`Fig. 6.`、`Figure 6`、`图 6` 等文本只用于识别和保留图注，不用于改变图片位置。

```python
{
    "type": "image",
    "page": 2,
    "column": "left",
    "bbox": [80, 300, 260, 450],
    "image_bytes": b"...",
    "parent_paragraph_id": 12,
    "caption": "Fig. 6. Architecture of the proposed model."
}
```

## 10. DOCX 段落格式

英文创建为普通 Word 段落，中文翻译创建为独立的一行一列表格；表格隐藏边框，
并使用浅蓝色单元格底色：

```python
from docx.shared import Cm, Pt


def format_paragraph(paragraph, after_points):
    paragraph.paragraph_format.first_line_indent = Cm(0.74)
    paragraph.paragraph_format.space_after = Pt(after_points)


def add_bilingual_pair(doc, english, chinese):
    english_paragraph = doc.add_paragraph(english)
    format_paragraph(english_paragraph, after_points=2)
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    # Set all cell borders to nil and apply the reference cell shading.
    table.cell(0, 0).text = chinese

    chinese_paragraph = doc.add_paragraph(chinese)
    format_paragraph(chinese_paragraph, after_points=10)
```

图片在中文段落之后作为独立块级内容插入：

```python
image_paragraph = doc.add_paragraph()
image_paragraph.alignment = 1
image_paragraph.add_run().add_picture(image_stream, width=image_width)
```

图片宽度根据 PDF 坐标换算，并限制在 DOCX 页面可用宽度内，同时保持原始比例。

## 11. 中文核心期刊风格基线

中文核心期刊没有完全统一的 DOCX 模板，不同期刊在字体、字号、页边距、标题层级、摘要和参考文献格式上可能不同。因此采用“**中文核心期刊风格基线 + 可配置期刊模板**”，不把某一本期刊的格式写死。

未指定目标期刊时，使用以下默认基线：

| 内容 | 默认格式 |
|---|---|
| 页面 | A4，纵向 |
| 页边距 | 上、下、左、右默认 2.54 cm，可配置 |
| 中文正文 | 宋体，五号（约 10.5 pt） |
| 英文正文 | Times New Roman，10.5 pt |
| 正文对齐 | 左对齐 |
| 正文行距 | 1.5 倍或固定值，可配置 |
| 首行缩进 | 2 个汉字宽度，英文和中文分别设置 |
| 中文标题 | 黑体，加粗，居中 |
| 英文标题 | Times New Roman，加粗，居中 |
| 章节标题 | 黑体或宋体加粗，不使用首行缩进 |
| 图片 | 居中，保持宽高比例，不超过版心宽度 |
| 图注 | 图片下方，居中，字号小于正文 |
| 表注 | 表格上方，格式与图注统一 |
| 页码 | 页面底部居中，由模板控制 |

推荐定义以下 Word 样式：

```text
CoreTitleChinese
CoreTitleEnglish
CoreAuthor
CoreAbstractChinese
CoreAbstractEnglish
CoreBodyEnglish
CoreBodyChinese
CoreHeading1
CoreHeading2
CoreFigureCaption
CoreTableCaption
CoreReference
```

格式配置优先级：

```text
指定期刊模板 > 用户配置 > 中文核心期刊默认基线
```

如果用户提供目标期刊投稿模板或投稿须知，应读取其中的字体、字号、页边距、标题格式和参考文献格式，并覆盖默认基线。未指定具体期刊时，只能称为“参考中文核心期刊风格”。

参考文献、公式、变量名、表格数据和图片内部文字默认保留原始结构，必要时作为独立后处理模块。

## 12. DOCX 输出布局策略

第一版建议输出单栏 DOCX：

```text
左栏英文段落
左栏中文段落
图片
右栏英文段落
右栏中文段落
```

DOCX 自动换行和分页机制与 PDF 不同。直接设置 DOCX 为两栏时，Word 可能将图片移动到另一栏或下一页，破坏图片与双语段落的对应关系。后续可以增加保留两栏外观的可选模式，但内容顺序和图片归属规则不变。

## 13. 扫描版 PDF

如果 PDF 页面没有可提取的文字，则先执行 OCR：

```text
扫描版 PDF
    ↓
OCRmyPDF 添加文字层
    ↓
PyMuPDF 提取 OCR 文字和坐标
    ↓
继续执行普通 PDF 版面分析
```

OCR 结果可能有识别错误，程序应记录警告，不得静默丢弃无法识别的文字或图片。

## 14. 项目结构

```text
paper2doc/
├── docs/
│   └── implementation-plan.md
├── pyproject.toml
├── paper2doc/
│   ├── __init__.py
│   ├── cli.py
│   ├── models.py
│   ├── pdf_reader.py
│   ├── text_extractor.py
│   ├── image_extractor.py
│   ├── layout_analyzer.py
│   ├── pdf_api.py
│   ├── relation_builder.py
│   ├── translator.py
│   ├── docx_writer.py
│   └── ocr.py
└── tests/
    ├── test_text_extraction.py
    ├── test_column_layout.py
    ├── test_image_relation.py
    └── test_docx_output.py
```

模块职责：

| 模块 | 职责 |
|---|---|
| `pdf_reader.py` | 打开 PDF、遍历页面和读取页面尺寸 |
| `text_extractor.py` | 提取文字块并合并为段落 |
| `image_extractor.py` | 提取图片并保存图片数据和图注 |
| `layout_analyzer.py` | 识别单栏、双栏、全宽区域和阅读顺序 |
| `relation_builder.py` | 按页面位置将图片关联到段落 |
| `translator.py` | 调用 OpenAI 兼容 API 翻译英文到中文 |
| `docx_writer.py` | 按双语内容序列生成 DOCX |
| `ocr.py` | 处理扫描版 PDF |
| `cli.py` | 提供 `paper2doc` 命令行入口 |

### 14.1 命令行入口注册

通过 `pyproject.toml` 注册命令：

```toml
[project.scripts]
paper2doc = "paper2doc.cli:main"
pdf2doc = "paper2doc.cli:main"
```

安装项目后，Conda 环境会将 `paper2doc` 加入 PATH；`pdf2doc` 作为兼容别名保留。

## 15. 实施阶段

### 第一阶段：基础转换

- 支持文字型 PDF。
- 提取英文段落。
- 提取图片。
- 生成单栏 DOCX。
- 实现英文段落和中文翻译成对输出。
- 提供 `paper2doc` 命令行入口，并保留 `pdf2doc` 兼容别名。

### 第二阶段：双栏和图片关联

- 识别左右栏。
- 处理跨栏元素。
- 按图片实际位置关联最近段落。
- 将图片放在英文和中文段落之后。
- 识别并保留图注。

### 第三阶段：OCR 和复杂版面

- 支持扫描版 PDF。
- 改进栏间空白区域识别。
- 支持跨页图片、表格和公式。
- 增加转换警告和人工检查信息。

## 16. 使用方式

以下是程序完成后的正式使用方式。

### 16.1 首次安装

```bash
conda create -n paper2doc \
  --override-channels \
  -c https://repo.anaconda.com/pkgs/main \
  python=3.11 pip -y
conda activate paper2doc
python -m pip install -e '.[ocr]'
brew install tesseract
```

如果环境已经创建：

```bash
conda activate paper2doc
python -m pip install -e '.[ocr]'
```

### 16.2 配置翻译服务

在项目根目录将模板 `.env.local` 复制为 `.env`：

```bash
cp .env.local .env
```

使用本地服务时改为：

```dotenv
OPENAI_API_KEY=local
OPENAI_BASE_URL=http://127.0.0.1:8000/v1
OPENAI_MODEL=local-model-name
```

### 16.3 直接执行转换

正式命令支持最简形式，直接将 PDF 路径作为位置参数：

```bash
paper2doc paper.pdf
```

如果不指定 `--output`，程序默认在输入 PDF 所在目录生成输出文件，并将文件名设置为：

```text
原文件名_bilingual.docx
```

例如：

```text
/Users/yfhao/Documents/papers/paper.pdf
→ /Users/yfhao/Documents/papers/paper_bilingual.docx
```

也可以使用 `--input` 和 `--output` 形式显式指定路径：

```bash
paper2doc \
  --input paper.pdf \
  --output paper_bilingual.docx
```

`--input` 支持任意绝对路径或相对路径，输入文件不需要位于项目目录中。相对路径以执行命令时的当前工作目录为基准：

```bash
paper2doc \
  --input /Users/yfhao/Documents/papers/paper.pdf \
  --output /Users/yfhao/Documents/results/paper_bilingual.docx
```

也可以使用相对路径访问项目外部文件：

```bash
paper2doc \
  --input ../papers/paper.pdf \
  --output ../results/paper_bilingual.docx
```

也可以只使用位置参数指定外部文件：

```bash
paper2doc /Users/yfhao/Documents/papers/paper.pdf
```

程序启动时应检查输入路径是否存在、是否为普通文件、是否可读，并在无效时给出明确错误。输出路径也可以位于其他目录；如果父目录不存在，应报错或根据命令行选项创建目录，不能静默写入其他位置。

默认输出路径的计算规则：

```python
from pathlib import Path


def resolve_output_path(input_path: Path, output_path: Path | None) -> Path:
    if output_path is not None:
        return output_path

    return input_path.with_name(f"{input_path.stem}_bilingual.docx")
```

如果默认输出文件已经存在，程序应默认报错并提示用户使用其他输出路径，或提供明确的 `--overwrite` 选项，不能未经确认静默覆盖已有文件。

也可以使用位置参数并显式指定输出：

```bash
paper2doc paper.pdf -o paper_bilingual.docx
```

CLI 规则：

- 输入支持位置参数 `paper2doc paper.pdf`，也支持 `--input paper.pdf`。
- 输出参数 `--output` 或 `-o` 可选。
- 默认显示 PDF 读取、OCR、段落处理和 DOCX 写入进度；`--no-progress` 可以关闭进度输出。
- 进度输出到 stderr，不影响标准输出中的最终输出路径。
- 翻译进度只在段落或图注成功处理后增加，翻译失败时不能伪造完成数量。
- 批量翻译期间显示当前批次、批次字符数和 API 等待状态；完整批次通过标记校验后才更新总体段落进度。
- 翻译请求默认按阅读顺序分批，建议每批 6000–7000 个英文字符；`--batch-min-size` 和 `--batch-size` 可以调整范围。
- 完整段落默认不拆分；无法满足最小值的超长段落或最后一批必须明确标记为低于最小值。
- 批量翻译必须保留段落 ID，并校验返回结果中的标记，不能因批量响应异常静默丢失译文。
- 批量响应标记异常或返回 502 等可重试的 HTTP 错误时，先对原批次重试两次，再按二分策略拆分；单段批量响应仍异常时退回逐段翻译，不能静默丢失译文。
- 每个成功批次都要原子写入 checkpoint；程序中断后下次执行复用已完成的段落、图注和表格单元格翻译，从未完成批次继续。
- checkpoint 必须校验 PDF 内容哈希、提取选项和翻译批次配置；只有 DOCX 原子写入成功后才删除，`--restart` 可以主动忽略旧 checkpoint。
- 默认过滤页面顶部或底部重复出现的独立数字/罗马数字页码；`--keep-page-numbers` 可以保留原始页码。
- 默认过滤第 1 页之后重复出现的短页眉/页脚文本；`--keep-running-headers` 可以保留原始运行页眉和页脚。
- 如果同时提供位置参数和 `--input`，程序应报错，避免输入来源不明确。
- 如果未提供输出参数，使用输入文件所在目录和 `<stem>_bilingual.docx` 文件名。
- 如果默认输出文件已存在，默认报错；覆盖已有文件必须显式使用 `--overwrite`。

程序应自动：

1. 识别单栏或双栏结构。
2. 按正常阅读顺序提取英文段落。
3. 根据页面实际位置关联图片。
4. 调用 OpenAI 兼容 API 翻译英文段落。
5. 生成“英文段落 → 中文段落 → 图片 → 图注”的 DOCX。
6. 将无法确定的内容写入日志。

调试时也可以使用模块方式：

```bash
python -m paper2doc.cli \
  --input paper.pdf \
  --output paper_bilingual.docx
```

断点续传相关选项：

```bash
paper2doc paper.pdf --restart
paper2doc paper.pdf --keep-checkpoint
paper2doc paper.pdf --checkpoint-dir ./checkpoints
```

默认 checkpoint 位于平台用户缓存目录：macOS 为
`~/Library/Caches/paper2doc/checkpoints/`，Windows 为
`%LOCALAPPDATA%\\paper2doc\\Cache\\checkpoints\\`，Linux 为
`~/.cache/paper2doc/checkpoints/`。

### 16.4 检查输出

打开生成的 `paper_bilingual.docx`，检查：

- 双栏内容是否按左栏到右栏排列。
- 每个英文段落下方是否紧跟中文翻译。
- 图片是否位于所属双语段落之后。
- 图片是否保持比例且没有超出版心。
- 图注是否紧跟图片。
- 标题、摘要、章节标题和参考文献是否符合目标期刊要求。

### 16.5 当前项目状态

项目已经实现 `paper2doc` 命令、PDF 解析器、翻译器和 DOCX 生成器，并保留 `pdf2doc` 兼容别名。安装项目后可以直接执行转换；首次验证可使用 `--no-translate` 进行离线测试，该模式不会调用翻译 API。

## 17. 验收标准

程序满足以下条件时，可认为核心需求实现：

1. 可以将普通文字型 PDF 转换为 DOCX。
2. PDF 中的主要图片没有丢失。
3. 双栏 PDF 的左栏和右栏阅读顺序正确。
4. 每个英文段落下方紧跟对应的中文翻译。
5. 英文使用普通 Word 段落，中文译文使用独立的一行一列表格。
6. 段落缩进和间距通过 DOCX 格式属性实现。
7. 图片根据实际页面位置放在对应双语段落之后。
8. 正文中的 `Fig. 6` 不会强行改变图片位置。
9. 图片图注能够被保留，必要时可以生成中文图注。
10. 无法确定图片归属或无法识别文字时，会产生明确提示。
11. 未指定目标期刊时，DOCX 使用可配置的中文核心期刊风格基线。
12. 指定目标期刊模板后，模板格式能够覆盖默认基线。
13. 安装项目后可以直接执行 `paper2doc paper.pdf`，并在输入 PDF 所在目录生成默认输出文件。
14. `--output` 指定时使用用户给定路径，不指定时使用 `<pdf_stem>_bilingual.docx`。
15. 翻译中断后重新执行时，不重复请求已经成功完成的 batch。
16. 所有翻译完成且 DOCX 成功写入后，checkpoint 自动删除。
