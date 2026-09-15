from __future__ import annotations

import re
from collections.abc import Iterable

from .layout_analyzer import assign_columns, assign_regions, classify_column, reading_order
from .models import BBox, ImageBlock, InlineFormula, Paragraph, TableBlock
from .table_extractor import table_contains_bbox
from .page_number_filter import filter_page_numbers
from .pdf_api import fitz
from .running_header_filter import filter_running_headers

CAPTION_RE = re.compile(r"^\s*(?:fig(?:ure)?|图)\s*[\w.-]*\s*[:.]?", re.I)


def _overlap(first: BBox, second: BBox) -> float:
    width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    area = width * height
    source = max((first[2] - first[0]) * (first[3] - first[1]), 1.0)
    return area / source


def _block_text(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        value = "".join(span.get("text", "") for span in line.get("spans", []))
        if value.strip():
            lines.append(value.strip())
    text = " ".join(lines).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _span_bbox(span: dict) -> BBox | None:
    value = span.get("bbox")
    if not value or len(value) < 4:
        return None
    return tuple(float(item) for item in value[:4])


def _line_bbox(line: dict) -> BBox | None:
    value = line.get("bbox")
    if value and len(value) >= 4:
        return tuple(float(item) for item in value[:4])
    spans = [_span_bbox(span) for span in line.get("spans", [])]
    spans = [span for span in spans if span]
    if not spans:
        return None
    return (
        min(span[0] for span in spans),
        min(span[1] for span in spans),
        max(span[2] for span in spans),
        max(span[3] for span in spans),
    )


def _same_text_line(first: BBox, second: BBox) -> bool:
    first_height = max(first[3] - first[1], 1.0)
    second_height = max(second[3] - second[1], 1.0)
    first_center = (first[1] + first[3]) / 2
    second_center = (second[1] + second[3]) / 2
    center_limit = max(first_height, second_height) * 0.55
    horizontal_gap = max(first[0] - second[2], second[0] - first[2], 0)
    return abs(first_center - second_center) <= center_limit and horizontal_gap <= 48


def _merge_fragmented_text_blocks(blocks: list[dict], page_width: float) -> list[dict]:
    """Reassemble text blocks split by inline math glyphs on the same line."""
    if len(blocks) < 2:
        return blocks

    line_entries: list[tuple[int, dict, BBox, str]] = []
    for block_index, block in enumerate(blocks):
        for line in block.get("lines", []):
            bbox = _line_bbox(line)
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            if bbox and text.strip():
                line_entries.append((block_index, line, bbox, text))
    if len(line_entries) < 2:
        return blocks

    parents = list(range(len(blocks)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    for index, (_block_index, _line, first_bbox, _text) in enumerate(line_entries):
        first_column = classify_column(first_bbox, page_width)
        for _other_index, (other_block_index, _other_line, second_bbox, _other_text) in enumerate(
            line_entries[index + 1 :],
            start=index + 1,
        ):
            if first_column != classify_column(second_bbox, page_width):
                continue
            if _same_text_line(first_bbox, second_bbox):
                union(line_entries[index][0], other_block_index)

    grouped: dict[int, list[int]] = {}
    for block_index in range(len(blocks)):
        grouped.setdefault(find(block_index), []).append(block_index)
    if all(len(group) == 1 for group in grouped.values()):
        return blocks

    merged: list[dict] = []
    for group in grouped.values():
        if len(group) == 1:
            merged.append(blocks[group[0]])
            continue

        group_set = set(group)
        group_lines = [
            entry
            for entry in line_entries
            if entry[0] in group_set
        ]
        line_groups: list[list[tuple[int, dict, BBox, str]]] = []
        for entry in group_lines:
            matching_group = next(
                (
                    current
                    for current in line_groups
                    if any(_same_text_line(entry[2], candidate[2]) for candidate in current)
                ),
                None,
            )
            if matching_group is None:
                line_groups.append([entry])
            else:
                matching_group.append(entry)

        merged_lines = []
        for line_group in sorted(
            line_groups,
            key=lambda current: min(item[2][1] for item in current),
        ):
            spans = []
            for _block_index, line, _bbox, _text in sorted(
                line_group,
                key=lambda current: (current[2][0], current[2][1]),
            ):
                spans.extend(line.get("spans", []))
            spans.sort(
                key=lambda span: (
                    _span_bbox(span)[0] if _span_bbox(span) else float("inf"),
                    _span_bbox(span)[1] if _span_bbox(span) else float("inf"),
                )
            )
            ordered_spans = []
            for span in spans:
                if ordered_spans:
                    previous = ordered_spans[-1]
                    previous_bbox = _span_bbox(previous)
                    current_bbox = _span_bbox(span)
                    previous_text = str(previous.get("text", ""))
                    current_text = str(span.get("text", ""))
                    horizontal_gap = (
                        current_bbox[0] - previous_bbox[2]
                        if previous_bbox and current_bbox
                        else 0
                    )
                    if (
                        horizontal_gap > 2
                        and previous_text
                        and current_text
                        and not previous_text[-1].isspace()
                        and not current_text[0].isspace()
                        and previous_text[-1] not in "([{"
                        and current_text[0] not in ",.;:!?)]}"
                    ):
                        ordered_spans.append({"text": " "})
                ordered_spans.append(span)
            merged_lines.append(
                {
                    "bbox": (
                        min(item[2][0] for item in line_group),
                        min(item[2][1] for item in line_group),
                        max(item[2][2] for item in line_group),
                        max(item[2][3] for item in line_group),
                    ),
                    "spans": ordered_spans,
                }
            )
        merged.append(
            {
                "type": 0,
                "bbox": (
                    min(blocks[index]["bbox"][0] for index in group),
                    min(blocks[index]["bbox"][1] for index in group),
                    max(blocks[index]["bbox"][2] for index in group),
                    max(blocks[index]["bbox"][3] for index in group),
                ),
                "lines": merged_lines,
            }
        )
    return merged


def _inline_formulas(block: dict) -> list[InlineFormula]:
    formulas: list[InlineFormula] = []
    for line in block.get("lines", []):
        spans = [
            span
            for span in line.get("spans", [])
            if str(span.get("text", "")).strip() and _span_bbox(span)
        ]
        consumed: set[int] = set()
        for index, base_span in enumerate(spans):
            if index in consumed:
                continue
            base_text = str(base_span.get("text", "")).strip()
            base_bbox = _span_bbox(base_span)
            if not base_bbox or len(base_text) > 2:
                continue
            base_size = float(base_span.get("size", base_bbox[3] - base_bbox[1]))
            subscript_parts = []
            superscript_parts = []
            modifier_indexes: set[int] = set()
            for modifier_index in range(index + 1, len(spans)):
                if modifier_index in consumed:
                    continue
                modifier_span = spans[modifier_index]
                modifier_text = str(modifier_span.get("text", "")).strip()
                modifier_bbox = _span_bbox(modifier_span)
                if (
                    not modifier_bbox
                    or not modifier_text
                    or len(modifier_text) > 3
                    or modifier_bbox[0] < base_bbox[0] - 1
                    or modifier_bbox[0] - base_bbox[2] > 2
                ):
                    continue
                modifier_size = float(
                    modifier_span.get("size", modifier_bbox[3] - modifier_bbox[1])
                )
                if modifier_size > base_size * 0.9:
                    continue
                base_height = base_bbox[3] - base_bbox[1]
                is_subscript = modifier_bbox[1] >= base_bbox[1] + base_height * 0.3
                is_superscript = modifier_bbox[3] <= base_bbox[3] - base_height * 0.25
                if not (is_subscript or is_superscript):
                    continue
                modifier_indexes.add(modifier_index)
                if is_subscript:
                    subscript_parts.append((modifier_bbox[1], modifier_text))
                if is_superscript:
                    superscript_parts.append((modifier_bbox[1], modifier_text))
            if not subscript_parts and not superscript_parts:
                continue
            subscript = "".join(text for _y, text in sorted(subscript_parts)) or None
            superscript = "".join(text for _y, text in sorted(superscript_parts)) or None
            formulas.append(
                InlineFormula(
                    text=base_text
                    + (superscript or "")
                    + (subscript or ""),
                    base=base_text,
                    subscript=subscript,
                    superscript=superscript,
                )
            )
            consumed.update(modifier_indexes)
    return formulas


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
                and blocker.bbox[1] >= previous.bbox[3] - 1
                and blocker.bbox[1] <= block.bbox[3]
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
    previous.inline_formulas.extend(block.inline_formulas)


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
        page_blocks = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            text = _block_text(block)
            if not text:
                continue
            bbox = tuple(float(value) for value in block["bbox"])
            if any(table_contains_bbox(table, bbox) for table in tables):
                continue
            if any(
                image.is_formula and _overlap(bbox, image.bbox) >= 0.5
                for image in images
            ):
                continue
            page_blocks.append(block)
        for block in _merge_fragmented_text_blocks(page_blocks, page.rect.width):
            text = _block_text(block)
            bbox = tuple(float(value) for value in block["bbox"])
            blocks.append(
                Paragraph(
                    id=next_id,
                    page=page_number,
                    bbox=bbox,
                    text=text,
                    is_caption=bool(CAPTION_RE.match(text)),
                    inline_formulas=_inline_formulas(block),
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
