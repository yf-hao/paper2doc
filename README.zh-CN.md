# paper2doc

`paper2doc` 用于将论文 PDF 转换为英中双语 DOCX 文档。程序提取英文段落
和图片，将每个英文段落翻译为中文，并将中文段落放在对应英文段落的下方。
图片根据其所在页面和实际几何位置关联到段落，而不是根据 `Fig.` 引用移动。

## 安装

创建独立的 Conda 环境，并通过项目的 `pyproject.toml` 安装依赖：

```bash
conda create -n paper2doc \
  --override-channels \
  -c https://repo.anaconda.com/pkgs/main \
  python=3.11 pip -y
conda activate paper2doc
python -m pip install -e '.[ocr]'
brew install tesseract
```

如果环境已经存在：

```bash
conda activate paper2doc
python -m pip install -e '.[ocr]'
```

激活环境后，先确认 Python 和命令都来自项目环境：

```bash
which python
which paper2doc
```

两个路径都应该包含 `/envs/paper2doc/`。如果 zsh 仍然解析到 Base 环境中
缓存的旧命令，请刷新命令缓存：

```bash
rehash
```

`pyproject.toml` 是 Python 依赖、可选 OCR 依赖和 CLI 命令入口的唯一配置
来源，不需要另外维护 `requirements.txt`。

## 配置翻译服务

`.env.local` 只作为模板。先将它复制为项目根目录下的 `.env`，然后修改其中
的占位配置：

```bash
cp .env.local .env
```

程序会自动从当前工作目录或其父目录读取 `.env`。`.env` 中已经定义的变量会
覆盖系统环境变量；`.env` 未定义的变量仍然可以通过系统环境变量提供。

`.env` 示例：

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=your-translation-model
```

翻译使用 OpenAI 兼容的 Chat Completions API，因此
`OPENAI_BASE_URL` 可以指向 OpenAI 官方接口、本地推理服务或其他兼容服务。

不要将 `.env` 或真实 API 密钥提交到版本库。

## 使用方法

最简形式是将 PDF 路径作为位置参数：

```bash
paper2doc paper.pdf
```

如果不指定 `--output`，程序会在输入 PDF 所在目录生成
`<文件名>_bilingual.docx`。例如：

```text
/path/to/paper.pdf
→ /path/to/paper_bilingual.docx
```

支持绝对路径和相对路径：

```bash
paper2doc /path/to/paper.pdf
paper2doc ../papers/paper.pdf
```

也可以显式指定输入和输出路径：

```bash
paper2doc \
  --input /path/to/paper.pdf \
  --output /path/to/results/paper_bilingual.docx
```

默认不会覆盖已有输出文件，必须显式使用 `--overwrite`：

```bash
paper2doc paper.pdf --overwrite
```

可以使用 `--no-translate` 进行离线提取测试。该模式不会调用翻译 API，
中文段落暂时与提取出的英文内容相同：

```bash
paper2doc paper.pdf --no-translate
```

翻译请求默认按照阅读顺序分批发送，建议每批保持在 6000–7000 个英文字符
之间。程序会保留段落 ID，因此 DOCX 中仍然是独立的英文段落和中文翻译表格，
不会把整篇文章合并成一个大段落。完整段落不会被拆分；如果最后一批无法达到
6000 个字符，进度中会明确标记。需要时可以调整范围：

```bash
paper2doc paper.pdf --batch-min-size 6000 --batch-size 7000
```

扫描版 PDF 需要安装可选 OCR 依赖，并使用 `--ocr`：

```bash
paper2doc scanned.pdf --ocr
```

程序默认删除在页面顶部或底部重复出现的独立页码。如果需要保留 PDF 原始
页码，可以使用：

```bash
paper2doc paper.pdf --keep-page-numbers
```

程序也会默认删除第 1 页之后重复出现的短页眉或页脚，例如期刊名、作者名和
卷期信息。如果需要保留这些原始页眉页脚，可以使用：

```bash
paper2doc paper.pdf --keep-running-headers
```

命令行会显示 PDF 读取、OCR、段落翻译和 DOCX 写入进度。进度输出到
stderr，因此标准输出中的最终文件路径仍然便于脚本读取。如需关闭进度：

```bash
paper2doc paper.pdf --no-progress
```

批量翻译时还会显示当前批次、字符数以及是否正在等待 API 响应。只有完整批次
通过段落标记校验后，总体段落进度才会增加。
如果批量响应格式异常，或服务端返回 502 等可重试的 HTTP 错误，程序会先
对原批次重试两次；仍然失败后再拆成更小批次重试，最后退回单段翻译。
单段仍然失败时才报告错误。

`pdf2doc` 仍然作为 `paper2doc` 的兼容别名保留。

## 输出规则

- 英文写入普通的 Word 段落。
- 每个中文译文单独写入一个一行一列的表格单元格，隐藏边框并使用浅蓝色底色，
  与参考 DOCX 保持一致。
- 正文和图注统一使用左对齐，不使用两端对齐。
- 图片插入到对应英中段落对之后。
- 图片根据页面、栏和实际几何位置关联到段落。
- 正文中的 `Fig. 6` 不会强行移动图片。
- 第一版输出单栏 DOCX，以保证阅读顺序。
- DOCX 使用可配置的 A4 中文核心期刊风格基线，包括页边距、字体、缩进和
  段落间距。
- 每个段落或图注成功翻译后，翻译进度才会增加。

## 开发测试

在 Conda 环境中运行测试：

```bash
conda activate paper2doc
python -m pytest -q
```
