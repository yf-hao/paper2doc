from __future__ import annotations

from pathlib import Path

from .image_extractor import extract_images
from .layout_analyzer import assign_columns, assign_regions, reading_order
from .models import ImageBlock, Paragraph, ScanInfo, TableBlock
from .ocr import detect_scan
from .pdf_api import fitz
from .relation_builder import associate_images
from .text_extractor import extract_paragraphs
from .table_extractor import extract_tables


def read_pdf(
    path: str | Path,
    remove_page_numbers: bool = True,
    remove_running_headers: bool = True,
) -> tuple[list[Paragraph], list[ImageBlock], list[TableBlock], ScanInfo]:
    path = Path(path)
    with fitz.open(path) as document:
        scan_info = detect_scan(document)
        tables = extract_tables(document)
        paragraphs = extract_paragraphs(
            document,
            remove_page_numbers=remove_page_numbers,
            remove_running_headers=remove_running_headers,
            tables=tables,
        )
        images = extract_images(document)
        paragraphs, images = associate_images(paragraphs, images)
        page_widths = {page_number: document[page_number].rect.width for page_number in range(len(document))}
        all_elements = [*paragraphs, *images, *tables]
        assign_columns(all_elements, page_widths)
        assign_regions(all_elements)
        ordered = reading_order(all_elements)
        paragraphs = [item for item in ordered if isinstance(item, Paragraph)]
        images = [item for item in ordered if isinstance(item, ImageBlock)]
        tables = [item for item in ordered if isinstance(item, TableBlock)]
    return paragraphs, images, tables, scan_info
