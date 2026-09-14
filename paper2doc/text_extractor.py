from __future__ import annotations

import re
from collections.abc import Iterable

from .layout_analyzer import assign_columns, assign_regions, reading_order
from .models import BBox, ImageBlock, Paragraph, TableBlock
from .table_extractor import table_contains_bbox
from .page_number_filter import filter_page_numbers
from .pdf_api import fitz
from .running_header_filter import filter_running_headers

CAPTION_RE = re.compile(r"^\s*(?:fig(?:ure)?|图)\s*[\w.-]*\s*[:.]?", re.I)


def _block_text(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        value = "".join(span.get("text", "") for span in line.get("spans", []))
        if value.strip():
            lines.append(value.strip())
    text = " ".join(lines).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def merge_text_blocks(
    blocks: Iterable[Paragraph],
    y_gap_factor: float = 1.8,
    tables: Iterable[TableBlock] | None = None,
    images: Iterable[ImageBlock] | None = None,
) -> list[Paragraph]:
    """Merge adjacent blocks that are clearly continuations in the same column."""
    result: list[Paragraph] = []
    tables = list(tables or [])
    images = list(images or [])
    blockers = [*tables, *images]
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
            and not any(
                blocker.page == block.page
                and blocker.bbox[1] >= previous.bbox[3]
                and blocker.bbox[3] <= block.bbox[1]
                and blocker.column in {block.column, "full"}
                for blocker in blockers
            )
        ):
            previous_height = max(previous.bbox[3] - previous.bbox[1], 1)
            vertical_gap = block.bbox[1] - previous.bbox[3]
            aligned = abs(block.bbox[0] - previous.bbox[0]) <= 12
            if 0 <= vertical_gap <= previous_height * y_gap_factor and aligned:
                _join_paragraph_text(previous, block)
                _append_layout_part(previous, block)
                previous.bbox = _union_bbox(previous.bbox, block.bbox)
                continue
        result.append(block)
    return result


SECTION_START_RE = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?|[A-Z]\.)\s+")
LIST_START_RE = re.compile(r"^(?:[-*•]|\(?\w+[.)])\s+")
TERMINAL_RE = re.compile(r"""[.!?。！？…][\s"'’”»)\]}】〕》』]*$""")
CONTINUATION_START_RE = re.compile(r"""^[,.;:!?，。；：！？、)\]}】〕》』'’”]""")


def _append_layout_part(previous: Paragraph, block: Paragraph) -> None:
    if not previous.layout_parts:
        previous.layout_parts.append((previous.page, previous.bbox, previous.column))
    if block.layout_parts:
        previous.layout_parts.extend(block.layout_parts)
    else:
        previous.layout_parts.append((block.page, block.bbox, block.column))


def _union_bbox(first: BBox, second: BBox) -> BBox:
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )


def _join_paragraph_text(previous: Paragraph, current: Paragraph) -> None:
    previous_text = previous.text.rstrip()
    current_text = current.text.lstrip()
    if previous_text.endswith(("-", "\u00ad")):
        previous.text = previous_text[:-1] + current_text
    elif current_text.startswith(tuple(",.;:!?，。；：！？、)]}】〕》』'’”")):
        previous.text = previous_text + current_text
    else:
        previous.text = f"{previous_text} {current_text}"


def _looks_like_new_structure(text: str) -> bool:
    return bool(SECTION_START_RE.match(text) or LIST_START_RE.match(text))


def _looks_like_continuation(previous: Paragraph, current: Paragraph) -> bool:
    previous_text = previous.text.rstrip()
    current_text = current.text.lstrip()
    if not previous_text or not current_text or _looks_like_new_structure(current_text):
        return False
    if previous_text.endswith(("-", "\u00ad")):
        return True
    if CONTINUATION_START_RE.match(current_text):
        return True
    if current_text[0].islower():
        return True
    if previous_text.endswith((",", ";", ":", "，", "；", "：")):
        return True
    return not TERMINAL_RE.search(previous_text)


def merge_boundary_paragraphs(
    paragraphs: Iterable[Paragraph],
    layout: Iterable[Paragraph | ImageBlock | TableBlock],
) -> list[Paragraph]:
    """Merge paragraph fragments split at a column or page boundary."""
    ordered_paragraphs = list(paragraphs)
    ordered_layout = list(layout)
    layout_positions = {id(item): index for index, item in enumerate(ordered_layout)}
    result: list[Paragraph] = []
    for current in ordered_paragraphs:
        previous = result[-1] if result else None
        same_page_column_break = (
            previous
            and previous.page == current.page
            and previous.column == "left"
            and current.column == "right"
            and previous.region == current.region
        )
        page_break = (
            previous
            and current.page == previous.page + 1
        )
        adjacent = (
            previous
            and layout_positions.get(id(current)) == layout_positions.get(id(previous), -2) + 1
        )
        if (
            previous
            and not previous.is_caption
            and not current.is_caption
            and adjacent
            and (same_page_column_break or page_break)
            and _looks_like_continuation(previous, current)
        ):
            _join_paragraph_text(previous, current)
            _append_layout_part(previous, current)
            continue
        result.append(current)
    return result


def extract_paragraphs(
    document: fitz.Document,
    remove_page_numbers: bool = True,
    remove_running_headers: bool = True,
    tables: Iterable[TableBlock] | None = None,
    images: Iterable[ImageBlock] | None = None,
) -> list[Paragraph]:
    blocks: list[Paragraph] = []
    tables = list(tables or [])
    images = list(images or [])
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
            if any(table_contains_bbox(table, bbox) for table in tables):
                continue
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
    layout_elements = [*blocks, *tables, *images]
    assign_columns(layout_elements, page_widths)
    assign_regions(layout_elements)
    merged = merge_text_blocks(blocks, tables=tables, images=images)
    ordered = reading_order(merged)
    layout = reading_order([*merged, *tables, *images])
    return merge_boundary_paragraphs(ordered, layout)
