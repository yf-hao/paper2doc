from __future__ import annotations

import argparse
from pathlib import Path

from .docx_writer import write_docx
from .ocr import detect_scan
from .ocr import run_ocr
from .pdf_reader import read_pdf
from .progress import NullProgress, TerminalProgress
from .translator import Translator, load_local_environment


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch size must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("batch size must be greater than zero")
    return parsed


def resolve_output_path(input_path: Path, output_path: Path | None = None) -> Path:
    input_path = Path(input_path)
    return Path(output_path) if output_path is not None else input_path.with_name(f"{input_path.stem}_bilingual.docx")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a research PDF to an English/Chinese DOCX.")
    parser.add_argument("input_positional", nargs="?", help="input PDF path")
    parser.add_argument("--input", dest="input_option", help="input PDF path")
    parser.add_argument("-o", "--output", type=Path, help="output DOCX path")
    parser.add_argument("--overwrite", action="store_true", help="overwrite an existing output file")
    parser.add_argument("--ocr", action="store_true", help="run OCRmyPDF for a scanned PDF when available")
    parser.add_argument("--no-translate", action="store_true", help="extract and write English text without API calls")
    parser.add_argument("--no-progress", action="store_true", help="disable progress output")
    parser.add_argument("--keep-page-numbers", action="store_true", help="keep standalone PDF page numbers")
    parser.add_argument("--keep-running-headers", action="store_true", help="keep repeated PDF headers and footers")
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=7000,
        help="maximum English characters per translation request (default: 7000)",
    )
    parser.add_argument(
        "--batch-min-size",
        type=positive_int,
        default=6000,
        help="recommended minimum English characters per batch (default: 6000)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input_positional and args.input_option:
        parser.error("provide input either positionally or with --input, not both")
    input_value = args.input_option or args.input_positional
    if not input_value:
        parser.error("an input PDF is required")
    if args.batch_min_size > args.batch_size:
        parser.error("--batch-min-size cannot be greater than --batch-size")
    input_path = Path(input_value).expanduser()
    if not input_path.is_file():
        parser.error(f"input PDF does not exist or is not a file: {input_path}")
    output_path = resolve_output_path(input_path, args.output)
    if output_path.exists() and not args.overwrite:
        parser.error(f"output already exists: {output_path}; use --overwrite to replace it")
    if output_path.parent != Path(".") and not output_path.parent.is_dir():
        parser.error(f"output directory does not exist: {output_path.parent}")

    progress = NullProgress() if args.no_progress else TerminalProgress()
    progress.stage("Reading PDF...")
    load_local_environment()
    paragraphs, images, scan_info = read_pdf(
        input_path,
        remove_page_numbers=not args.keep_page_numbers,
        remove_running_headers=not args.keep_running_headers,
    )
    progress.stage(f"Read PDF: found {len(paragraphs)} paragraphs and {len(images)} images")
    if scan_info.is_scan:
        if not args.ocr:
            parser.error(scan_info.warning)
        ocr_path = input_path.with_name(f"{input_path.stem}_ocr.pdf")
        try:
            progress.stage("Running OCR...")
            try:
                run_ocr(input_path, ocr_path)
            except Exception as exc:
                parser.error(str(exc))
            paragraphs, images, scan_info = read_pdf(
                ocr_path,
                remove_page_numbers=not args.keep_page_numbers,
                remove_running_headers=not args.keep_running_headers,
            )
            progress.stage(f"OCR completed: found {len(paragraphs)} paragraphs and {len(images)} images")
        finally:
            ocr_path.unlink(missing_ok=True)
        if scan_info.is_scan:
            parser.error("OCR completed but no text layer was produced; refusing to generate a lossy DOCX")

    class IdentityTranslator:
        def translate(self, text: str) -> str:
            return text

    if args.no_translate:
        translator = IdentityTranslator()
    else:
        try:
            translator = Translator()
        except RuntimeError as exc:
            parser.error(str(exc))
    write_docx(
        paragraphs,
        images,
        translator,
        output_path,
        progress=progress,
        translation_description="Processing paragraphs" if args.no_translate else "Translating paragraphs",
        batch_size=args.batch_size,
        batch_min_size=args.batch_min_size,
    )
    progress.stage("Writing DOCX... done")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
