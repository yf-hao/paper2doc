# paper2doc

`paper2doc` converts research PDFs into single-column bilingual DOCX files. It
extracts English paragraphs and images, translates each paragraph into Chinese,
and places the Chinese paragraph directly below the English paragraph. Images
are associated by their page and geometric position, not by `Fig.` references.

## Install

Create an isolated Conda environment and install the project from
`pyproject.toml`:

```bash
conda create -n paper2doc \
  --override-channels \
  -c https://repo.anaconda.com/pkgs/main \
  python=3.11 pip -y
conda activate paper2doc
python -m pip install -e '.[ocr]'
brew install tesseract
```

If the environment already exists:

```bash
conda activate paper2doc
python -m pip install -e '.[ocr]'
```

After activation, verify that both commands use the project environment:

```bash
which python
which paper2doc
```

Both paths should contain `/envs/paper2doc/`. If zsh still resolves an older
Base-environment command, refresh its command cache:

```bash
rehash
```

`pyproject.toml` is the single source of truth for Python dependencies, the
optional OCR dependencies, and the CLI entry points. A separate
`requirements.txt` file is not needed.

## Configure the Translation Service

`.env.local` is a template only. Copy it to `.env` in the project root, then
replace the placeholder values:

```bash
cp .env.local .env
```

The application automatically reads `.env` from the current working directory
or one of its parent directories. Values defined in `.env` take precedence
over existing environment variables. Variables not defined in `.env` can still
be supplied through the environment.

Example `.env`:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=your-translation-model
```

The translation client uses the OpenAI-compatible Chat Completions API, so
`OPENAI_BASE_URL` can point to the official API, a local inference server, or a
third-party compatible service.

Do not commit `.env` or real API keys.

## Usage

The shortest form accepts the PDF as a positional argument:

```bash
paper2doc paper.pdf
```

If `--output` is omitted, the output is written beside the input as
`<stem>_bilingual.docx`. For example:

```text
/path/to/paper.pdf
→ /path/to/paper_bilingual.docx
```

Absolute and relative input paths are supported:

```bash
paper2doc /path/to/paper.pdf
paper2doc ../papers/paper.pdf
```

Explicit input and output paths are also supported:

```bash
paper2doc \
  --input /path/to/paper.pdf \
  --output /path/to/results/paper_bilingual.docx
```

Existing output files are not overwritten unless `--overwrite` is explicit:

```bash
paper2doc paper.pdf --overwrite
```

Use `--no-translate` for an offline extraction smoke test. In this mode the
Chinese paragraph is temporarily identical to the extracted English text and
no translation API is called:

```bash
paper2doc paper.pdf --no-translate
```

Translation requests are batched in reading order, with a recommended range of
6,000–7,000 English characters per request. Paragraph boundaries and IDs are
preserved, so the DOCX still contains separate English paragraphs and Chinese
translation tables. Complete paragraphs are not split; an unavoidable short
final batch is marked in the progress output. Adjust the limits when needed:

```bash
paper2doc paper.pdf --batch-min-size 6000 --batch-size 7000
```

For a scanned PDF, install the optional OCR dependencies and use `--ocr`:

```bash
paper2doc scanned.pdf --ocr
```

Standalone page numbers detected at repeated header/footer positions are
removed by default. Keep them when needed:

```bash
paper2doc paper.pdf --keep-page-numbers
```

Repeated short running headers and footers, such as journal metadata, are also
removed after the first page by default. Keep them when needed:

```bash
paper2doc paper.pdf --keep-running-headers
```

The CLI reports PDF reading, OCR, paragraph translation, and DOCX writing
progress. Progress is written to stderr so the final output path remains easy
to capture. Disable progress output when needed:

```bash
paper2doc paper.pdf --no-progress
```

During batched translation it also shows the current batch, character count,
and whether the program is waiting for the API response. Overall paragraph
progress advances only after a complete batch passes marker validation.
If a batch response is malformed or the provider returns a retryable HTTP
error such as 502, the program first retries the same batch twice. It then
retries smaller batches and ultimately falls back to single-paragraph
translation before reporting failure.

Successful translation batches are saved to a checkpoint in the platform user
cache. If the process is interrupted, the next run restores completed
paragraphs, captions, and table-cell translations and resumes from the first
unfinished batch. The checkpoint is removed only after the DOCX is written
successfully. Use `--restart` to ignore an existing checkpoint,
`--keep-checkpoint` to retain it after success, or `--checkpoint-dir` to choose
another directory:

```bash
paper2doc paper.pdf --restart
paper2doc paper.pdf --checkpoint-dir ./checkpoints
```

### CLI parameters

| Parameter | Description | Default |
| --- | --- | --- |
| `input.pdf` | Input PDF path as a positional argument. Cannot be combined with `--input`. | Required |
| `--input PATH` | Input PDF path. | — |
| `-o PATH`, `--output PATH` | Output DOCX path. | `<input_stem>_bilingual.docx` beside the PDF |
| `--overwrite` | Allow an existing output DOCX to be replaced. | Disabled |
| `--ocr` | Run OCRmyPDF for a scanned PDF. Requires the optional OCR dependencies and Tesseract. | Disabled |
| `--no-translate` | Extract and write English content without calling the translation API. | Disabled |
| `--no-progress` | Disable progress output. | Disabled |
| `--keep-page-numbers` | Keep standalone numeric or Roman page numbers detected in headers/footers. | Removed |
| `--keep-running-headers` | Keep repeated short running headers and footers. | Removed after page 1 |
| `--batch-size N` | Maximum English characters per translation request. | `7000` |
| `--batch-min-size N` | Recommended minimum batch size. Must not exceed `--batch-size`. | `6000` |
| `--restart` | Ignore the matching checkpoint and translate from the beginning. | Disabled |
| `--keep-checkpoint` | Keep the checkpoint after the DOCX is written successfully. | Disabled |
| `--checkpoint-dir PATH` | Directory for checkpoint files. | Platform user cache |
| `-h`, `--help` | Show the complete command help. | — |

`pdf2doc` remains available as a compatibility alias for `paper2doc`.

## Output Behavior

- English is written as a normal Word paragraph.
- Each Chinese translation is written in its own one-cell table with no borders
  and light-blue shading, matching the reference DOCX.
- Text paragraphs and captions use left alignment rather than full justification.
- Images are inserted after the associated English/Chinese paragraph pair.
- Image association uses page, column, and geometric position.
- A `Fig. 6` reference does not move an image.
- The first version outputs a single-column DOCX to preserve reading order.
- Text-based PDF tables are detected with PyMuPDF table APIs when available,
  and with horizontal-rule plus whitespace/column inference for common tables
  without vertical rules. Table text is removed from ordinary paragraph
  extraction, so it is not duplicated.
- Successfully extracted tables are written as native Word grids, followed by
  a matching native Chinese grid. Captions remain above the table; empty cells,
  approximate widths, header rows, spans, and horizontal rules are preserved
  where the PDF exposes them.
- If a table can be recognized but its cell grid cannot be recovered, the
  original table region is inserted as an image rather than silently dropped.
- The DOCX uses an A4, Chinese-core-style baseline with configurable margins,
  fonts, indentation, and paragraph spacing.
- Translation progress advances after each paragraph or caption is translated
  successfully.

## Development

Run the test suite from the Conda environment:

```bash
conda activate paper2doc
python -m pytest -q
```
