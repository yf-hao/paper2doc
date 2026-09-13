from __future__ import annotations

from pathlib import Path

from .image_extractor import extract_images
from .models import ImageBlock, Paragraph, ScanInfo
from .ocr import detect_scan
from .pdf_api import fitz
from .relation_builder import associate_images
from .text_extractor import extract_paragraphs


def read_pdf(
    path: str | Path,
    remove_page_numbers: bool = True,
    remove_running_headers: bool = True,
) -> tuple[list[Paragraph], list[ImageBlock], ScanInfo]:
    path = Path(path)
    with fitz.open(path) as document:
        scan_info = detect_scan(document)
        paragraphs = extract_paragraphs(
            document,
            remove_page_numbers=remove_page_numbers,
            remove_running_headers=remove_running_headers,
        )
        images = extract_images(document)
        paragraphs, images = associate_images(paragraphs, images)
    return paragraphs, images, scan_info
