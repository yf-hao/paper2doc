from __future__ import annotations

import re
from collections.abc import Iterable

from .layout_analyzer import assign_columns, assign_regions, reading_order
from .models import Paragraph
from .page_number_filter import filter_page_numbers
from .pdf_api import fitz
from .running_header_filter import filter_running_headers

CAPTION_RE = re.compile(r"^\s*(?:fig(?:ure)?|table|图|表)\s*[\w.-]*\s*[:.]?", re.I)


def _block_text(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        value = "".join(span.get("text", "") for span in line.get("spans", []))
        if value.strip():
            lines.append(value.strip())
    text = " ".join(lines).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def merge_text_blocks(blocks: Iterable[Paragraph], y_gap_factor: float = 1.8) -> list[Paragraph]:
    """Merge adjacent blocks that are clearly continuations in the same column."""
    result: list[Paragraph] = []
    for block in sorted(blocks, key=lambda item: (item.page, item.region, item.bbox[1], item.bbox[0])):
        if not block.text:
            continue
        previous = result[-1] if result else None
        if (
            previous
            and not previous.is_caption
            and not block.is_caption
            and previous.page == block.page
            and previous.column == block.column
        ):
            previous_height = max(previous.bbox[3] - previous.bbox[1], 1)
            vertical_gap = block.bbox[1] - previous.bbox[3]
            aligned = abs(block.bbox[0] - previous.bbox[0]) <= 12
            if 0 <= vertical_gap <= previous_height * y_gap_factor and aligned:
                joiner = "" if previous.text.endswith("-") else " "
                if previous.text.endswith("-"):
                    previous.text = previous.text[:-1]
                previous.text += joiner + block.text
                previous.bbox = (
                    min(previous.bbox[0], block.bbox[0]),
                    min(previous.bbox[1], block.bbox[1]),
                    max(previous.bbox[2], block.bbox[2]),
                    max(previous.bbox[3], block.bbox[3]),
                )
                continue
        result.append(block)
    return result


def extract_paragraphs(
    document: fitz.Document,
    remove_page_numbers: bool = True,
    remove_running_headers: bool = True,
) -> list[Paragraph]:
    blocks: list[Paragraph] = []
    page_widths = {}
    next_id = 1
    for page_number, page in enumerate(document):
        page_widths[page_number] = page.rect.width
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            text = _block_text(block)
            if not text:
                continue
            bbox = tuple(float(value) for value in block["bbox"])
            blocks.append(
                Paragraph(
                    id=next_id,
                    page=page_number,
                    bbox=bbox,
                    text=text,
                    is_caption=bool(CAPTION_RE.match(text)),
                )
            )
            next_id += 1
    if remove_page_numbers:
        blocks = filter_page_numbers(blocks, {page: (width, document[page].rect.height) for page, width in page_widths.items()})
    if remove_running_headers:
        blocks = filter_running_headers(
            blocks,
            {page: (width, document[page].rect.height) for page, width in page_widths.items()},
        )
    assign_columns(blocks, page_widths)
    assign_regions(blocks)
    merged = merge_text_blocks(blocks)
    return reading_order(merged)
