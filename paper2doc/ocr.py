from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .models import ScanInfo
from .pdf_api import fitz


def detect_scan(document: fitz.Document) -> ScanInfo:
    pages_without_text = []
    for number, page in enumerate(document):
        text = page.get_text("text").strip()
        if not text:
            pages_without_text.append(number)
    is_scan = bool(pages_without_text) and len(pages_without_text) == document.page_count
    warning = (
        "This PDF appears to be a scanned document with no extractable text. "
        "Use --ocr if OCRmyPDF is installed; otherwise no text can be translated."
        if is_scan else None
    )
    return ScanInfo(is_scan=is_scan, pages_without_text=pages_without_text, warning=warning)


def run_ocr(input_path: Path, output_path: Path) -> Path:
    executable = shutil.which("ocrmypdf")
    if not executable:
        raise RuntimeError("OCR requested, but the ocrmypdf executable is not installed")
    subprocess.run([executable, str(input_path), str(output_path)], check=True)
    return output_path
