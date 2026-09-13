from __future__ import annotations

import re
from collections import defaultdict
from bisect import bisect_right
from statistics import median
from .models import BBox, TableBlock, TableCell

TABLE_CAPTION_RE = re.compile(r"^\s*(?:table|表)\s*[\w.-]*\s*[:.]?", re.I)


def _bbox(value) -> BBox:
    if hasattr(value, "bbox"):
        value = value.bbox
    return tuple(float(item) for item in value[:4])


def _overlap(a: BBox, b: BBox) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = width * height
    source = max((a[2] - a[0]) * (a[3] - a[1]), 1.0)
    return area / source


def _text_from_block(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        value = "".join(span.get("text", "") for span in line.get("spans", []))
        if value.strip():
            lines.append(value.strip())
    text = ""
    for line in lines:
        if text.endswith("-") and line[:1].islower() and text[-2:-1].isalpha():
            text = text[:-1] + line
        else:
            text = f"{text} {line}".strip()
    return re.sub(r"\s+", " ", text).strip()


def _point(value) -> tuple[float, float]:
    if hasattr(value, "x") and hasattr(value, "y"):
        return float(value.x), float(value.y)
    return float(value[0]), float(value[1])


def _page_text_blocks(page) -> list[tuple[BBox, str]]:
    result = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") == 0:
            text = _text_from_block(block)
            if text:
                result.append((_bbox(block["bbox"]), text))
    return result


def _horizontal_lines(page) -> list[tuple[float, float, float]]:
    lines = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return lines
    for drawing in drawings or []:
        for item in drawing.get("items", []):
            if not item:
                continue
            if item[0] == "l" and len(item) >= 3:
                start, end = item[1], item[2]
                x0, y0 = _point(start)
                x1, y1 = _point(end)
                if abs(y1 - y0) <= 2 and abs(x1 - x0) >= 20:
                    lines.append((min(x0, x1), max(x0, x1), (y0 + y1) / 2))
        rect = drawing.get("rect")
        if rect is not None:
            x0, y0, x1, y1 = map(float, rect)
            if abs(y1 - y0) <= 2 and x1 - x0 >= 20:
                lines.append((x0, x1, (y0 + y1) / 2))
    return lines


def _cluster(values: list[float], tolerance: float = 12) -> list[float]:
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and value - sum(groups[-1]) / len(groups[-1]) <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _pixmap(page, bbox: BBox) -> bytes | None:
    try:
        return page.get_pixmap(clip=bbox, alpha=False).tobytes("png")
    except Exception:
        return None


def _caption(page, table_bbox: BBox, text_blocks: list[tuple[BBox, str]]) -> tuple[str | None, BBox | None]:
    candidates = [
        (bbox, text)
        for bbox, text in text_blocks
        if TABLE_CAPTION_RE.match(text)
        and bbox[3] <= table_bbox[1] + 4
        and table_bbox[1] - bbox[3] <= 120
    ]
    if not candidates:
        return None, None
    bbox, text = min(candidates, key=lambda item: table_bbox[1] - item[0][3])
    return text, bbox


def _page_words(page) -> list[tuple[float, float, float, float, str]]:
    try:
        raw_words = page.get_text("words")
    except Exception:
        return []
    if not isinstance(raw_words, list):
        return []
    words = []
    for word in raw_words:
        if len(word) < 5:
            continue
        text = str(word[4]).strip()
        if not text:
            continue
        words.append((float(word[0]), float(word[1]), float(word[2]), float(word[3]), text))
    return words


def _group_words_by_line(
    words: list[tuple[float, float, float, float, str]],
) -> list[list[tuple[float, float, float, float, str]]]:
    lines: list[list[tuple[float, float, float, float, str]]] = []
    for word in sorted(words, key=lambda item: (item[1], item[0])):
        if lines:
            average_y = sum(item[1] for item in lines[-1]) / len(lines[-1])
            if abs(word[1] - average_y) <= 2:
                lines[-1].append(word)
                continue
        lines.append([word])
    return [sorted(line, key=lambda item: item[0]) for line in lines]


def _join_lines(lines: list[str]) -> str:
    text = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if text and (text.endswith("-") or text.endswith("\u00ad")) and line[:1].islower():
            text = text[:-1] + line
        else:
            text = f"{text} {line}".strip()
    return re.sub(r"\s+", " ", text).strip()


def _caption_candidates(text_blocks: list[tuple[BBox, str]]) -> list[tuple[BBox, str]]:
    return [(bbox, text) for bbox, text in text_blocks if TABLE_CAPTION_RE.match(text)]


def _line_table_from_words(
    page,
    page_number: int,
    table_id: int,
    text_blocks: list[tuple[BBox, str]],
    words: list[tuple[float, float, float, float, str]],
) -> list[TableBlock]:
    lines = _horizontal_lines(page)
    if len(lines) < 2:
        return []
    lines.sort(key=lambda item: item[2])
    grouped: list[list[tuple[float, float, float]]] = []
    for line in lines:
        if (
            grouped
            and abs(line[2] - grouped[-1][-1][2]) <= 3
            and line[0] <= max(item[1] for item in grouped[-1]) + 5
            and line[1] >= min(item[0] for item in grouped[-1]) - 5
        ):
            grouped[-1].append(line)
        else:
            grouped.append([line])
    horizontal_lines = [
        (min(line[0] for line in group), max(line[1] for line in group), sum(line[2] for line in group) / len(group))
        for group in grouped
    ]
    captions = _caption_candidates(text_blocks)
    tables: list[TableBlock] = []
    next_table_id = table_id
    for caption_index, (caption_bbox, caption_text) in enumerate(captions):
        next_caption_y = min(
            (
                candidate_bbox[1]
                for index, (candidate_bbox, _text) in enumerate(captions)
                if index != caption_index
                and candidate_bbox[1] > caption_bbox[1]
                and candidate_bbox[0] < caption_bbox[2] + 20
                and candidate_bbox[2] > caption_bbox[0] - 20
            ),
            default=float("inf"),
        )
        candidate_lines = [
            line
            for line in horizontal_lines
            if line[2] >= caption_bbox[3] - 4
            and line[2] < next_caption_y
            and line[1] > caption_bbox[0]
            and line[0] < caption_bbox[2]
        ]
        if len(candidate_lines) < 2:
            continue
        table_bbox = (
            min(line[0] for line in candidate_lines),
            min(line[2] for line in candidate_lines),
            max(line[1] for line in candidate_lines),
            max(line[2] for line in candidate_lines),
        )
        table_words = [
            word
            for word in words
            if word[3] >= table_bbox[1] - 2
            and word[1] <= table_bbox[3] + 2
            and word[2] > table_bbox[0]
            and word[0] < table_bbox[2]
        ]
        word_lines = _group_words_by_line(table_words)
        if not word_lines:
            continue
        first_line_y = candidate_lines[0][2]
        second_line_y = candidate_lines[1][2]
        header_lines = [
            line
            for line in word_lines
            if first_line_y - 2 <= line[0][1] <= second_line_y + 2
        ]
        if not header_lines:
            header_lines = [word_lines[0]]
        header_groups: list[list[tuple[float, float, float, float, str]]] = []
        for line in header_lines:
            line_groups: list[list[tuple[float, float, float, float, str]]] = []
            for word in line:
                if line_groups and word[0] - line_groups[-1][-1][2] <= 12:
                    line_groups[-1].append(word)
                else:
                    line_groups.append([word])
            for line_group in line_groups:
                matching_group = next(
                    (
                        group
                        for group in header_groups
                        if max(word[0] for word in line_group) <= max(word[2] for word in group)
                        and min(word[2] for word in line_group) >= min(word[0] for word in group)
                    ),
                    None,
                )
                if matching_group is None:
                    header_groups.append(line_group)
                else:
                    matching_group.extend(line_group)
        header_groups.sort(key=lambda group: min(word[0] for word in group))
        if len(header_groups) < 2:
            continue
        column_starts = [min(word[0] for word in group) for group in header_groups]
        boundaries = [table_bbox[0]]
        for left_start, right_start in zip(column_starts, column_starts[1:]):
            left_words = [word for word in table_words if word[0] >= left_start and word[0] < right_start]
            right_words = [word for word in table_words if word[0] >= right_start]
            if left_words and right_words:
                boundaries.append((max(word[2] for word in left_words) + min(word[0] for word in right_words)) / 2)
            else:
                boundaries.append((left_start + right_start) / 2)
        boundaries.append(table_bbox[2])

        def column_for_word(word) -> int:
            return min(len(column_starts) - 1, max(0, bisect_right(column_starts, word[0]) - 1))

        line_y = [line[0][1] for line in word_lines]
        gaps = [right - left for left, right in zip(line_y, line_y[1:]) if right - left > 0]
        line_gap = median(gaps) if gaps else 8
        first_column_lines = [
            line[0][1]
            for line in word_lines
            if line[0][1] > second_line_y + 2
            and any(
                column_for_word(word) == 0
                for word in line
            )
        ]
        row_starts: list[float] = [first_line_y]
        for y in first_column_lines:
            if y - row_starts[-1] > max(4, line_gap * 1.6):
                row_starts.append(y)
        if len(row_starts) == 1:
            for y in line_y:
                if y > second_line_y + 2 and y - row_starts[-1] > max(4, line_gap * 1.6):
                    row_starts.append(y)
        if len(row_starts) < 2:
            continue
        row_bounds = [*row_starts, table_bbox[3]]
        cell_lines: dict[tuple[int, int], dict[float, list[tuple[float, float, float, float, str]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for line in word_lines:
            y = line[0][1]
            row = min(len(row_starts) - 1, max(0, bisect_right(row_starts, y) - 1))
            for word in line:
                column = column_for_word(word)
                cell_lines[(row, column)][y].append(word)
        cells: list[TableCell] = []
        for row in range(len(row_starts)):
            for column in range(len(boundaries) - 1):
                lines_for_cell = cell_lines.get((row, column), {})
                text_lines = [
                    " ".join(word[4] for word in sorted(words_on_line, key=lambda item: item[0]))
                    for _y, words_on_line in sorted(lines_for_cell.items())
                ]
                cells.append(
                    TableCell(
                        row=row,
                        column=column,
                        bbox=(
                            boundaries[column],
                            row_bounds[row],
                            boundaries[column + 1],
                            row_bounds[row + 1],
                        ),
                        text=_join_lines(text_lines),
                        is_header=row == 0,
                    )
                )
        tables.append(
            TableBlock(
                id=next_table_id,
                page=page_number,
                bbox=table_bbox,
                rows=len(row_starts),
                columns=len(boundaries) - 1,
                cells=cells,
                caption=caption_text,
                caption_bbox=caption_bbox,
                horizontal_rules=True,
                vertical_rules=False,
            )
        )
        next_table_id += 1
    return tables


def _native_tables(page, page_number: int, start_id: int, text_blocks) -> list[TableBlock]:
    finder = getattr(page, "find_tables", None)
    if not callable(finder):
        return []
    try:
        found = finder()
        candidates = getattr(found, "tables", found or [])
    except Exception:
        return []
    result = []
    for offset, table in enumerate(candidates):
        table_bbox = _bbox(getattr(table, "bbox", getattr(table, "rect", (0, 0, 0, 0))))
        if table_bbox[2] <= table_bbox[0] or table_bbox[3] <= table_bbox[1]:
            continue
        try:
            extracted = table.extract()
        except Exception:
            extracted = []
        raw_cells = getattr(table, "cells", None) or []
        cells: list[TableCell] = []
        row_count = len(extracted or [])
        col_count = max((len(row) for row in (extracted or [])), default=0)
        nonempty_count = sum(bool(str(value or "").strip()) for row in (extracted or []) for value in row)
        if row_count < 2 or col_count < 2 or nonempty_count < max(2, row_count * col_count * 0.1):
            continue
        for row_index, row in enumerate(extracted or []):
            for col_index, value in enumerate(row):
                cell_bbox = table_bbox
                cell_index = row_index * col_count + col_index if col_count else -1
                raw_cell = raw_cells[cell_index] if 0 <= cell_index < len(raw_cells) else None
                row_span = col_span = 1
                if raw_cell is not None:
                    if isinstance(raw_cell, dict):
                        cell_bbox = _bbox(raw_cell.get("bbox", table_bbox))
                        row_span = int(raw_cell.get("row_span", 1))
                        col_span = int(raw_cell.get("col_span", 1))
                    else:
                        cell_bbox = _bbox(raw_cell)
                cells.append(
                    TableCell(
                        row_index,
                        col_index,
                        cell_bbox,
                        str(value or "").strip(),
                        row_span=row_span,
                        col_span=col_span,
                    )
                )
        header = getattr(table, "header", None)
        header_rows = 1 if header is not None and getattr(header, "names", None) else 0
        for cell in cells:
            cell.is_header = cell.row < header_rows
        caption, caption_bbox = _caption(page, table_bbox, text_blocks)
        fallback = _pixmap(page, table_bbox) if not cells else None
        result.append(
            TableBlock(
                id=start_id + offset,
                page=page_number,
                bbox=table_bbox,
                rows=row_count,
                columns=col_count,
                cells=cells,
                caption=caption,
                caption_bbox=caption_bbox,
                horizontal_rules=True,
                vertical_rules=True,
                fallback_image_bytes=fallback,
            )
        )
    return result


def _line_table(page, page_number: int, table_id: int, text_blocks) -> TableBlock | None:
    lines = _horizontal_lines(page)
    if len(lines) < 2:
        return None
    lines.sort(key=lambda item: item[2])
    grouped: list[list[tuple[float, float, float]]] = []
    for line in lines:
        if grouped and abs(line[2] - grouped[-1][-1][2]) <= 3:
            grouped[-1].append(line)
        else:
            grouped.append([line])
    if len(grouped) < 2:
        return None
    y_lines = [sum(line[2] for line in group) / len(group) for group in grouped]
    x0 = min(line[0] for line in lines)
    x1 = max(line[1] for line in lines)
    table_bbox = (x0, y_lines[0], x1, y_lines[-1])
    inside = [(bbox, text) for bbox, text in text_blocks if _overlap(bbox, table_bbox) > 0.05]
    if not inside:
        return None
    starts = _cluster([bbox[0] for bbox, _text in inside])
    if len(starts) < 2:
        caption, caption_bbox = _caption(page, table_bbox, text_blocks)
        return TableBlock(
            id=table_id,
            page=page_number,
            bbox=table_bbox,
            rows=max(1, len(y_lines) - 1),
            columns=1,
            caption=caption,
            caption_bbox=caption_bbox,
            horizontal_rules=True,
            vertical_rules=False,
            fallback_image_bytes=_pixmap(page, table_bbox),
        )
    starts = starts[: max(len(starts), 1)]
    boundaries = [x0]
    boundaries.extend((left + right) / 2 for left, right in zip(starts, starts[1:]))
    boundaries.append(x1)
    cells_by_key: dict[tuple[int, int], list[tuple[BBox, str]]] = defaultdict(list)
    for bbox, text in inside:
        row = min(len(y_lines) - 2, max(0, next((i for i in range(len(y_lines) - 1) if bbox[1] < y_lines[i + 1]), len(y_lines) - 2)))
        center = (bbox[0] + bbox[2]) / 2
        col = min(len(boundaries) - 2, max(0, next((i for i in range(len(boundaries) - 1) if center < boundaries[i + 1]), len(boundaries) - 2)))
        cells_by_key[(row, col)].append((bbox, text))
    cells = []
    for row in range(len(y_lines) - 1):
        for col in range(len(boundaries) - 1):
            values = cells_by_key.get((row, col), [])
            if values:
                boxes = [item[0] for item in values]
                cell_bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
                text = " ".join(item[1] for item in values)
            else:
                cell_bbox = (boundaries[col], y_lines[row], boundaries[col + 1], y_lines[row + 1])
                text = ""
            cells.append(TableCell(row, col, cell_bbox, text))
    caption, caption_bbox = _caption(page, table_bbox, text_blocks)
    return TableBlock(
        id=table_id,
        page=page_number,
        bbox=table_bbox,
        rows=len(y_lines) - 1,
        columns=len(boundaries) - 1,
        cells=cells,
        caption=caption,
        caption_bbox=caption_bbox,
        horizontal_rules=True,
        vertical_rules=False,
        fallback_image_bytes=None,
    )


def extract_tables(document) -> list[TableBlock]:
    """Extract captioned PDF tables from native grids or horizontal rules."""
    tables: list[TableBlock] = []
    next_id = 1
    for page_number, page in enumerate(document):
        text_blocks = _page_text_blocks(page)
        words = _page_words(page)
        if words:
            line_tables = _line_table_from_words(page, page_number, next_id, text_blocks, words)
            if line_tables:
                tables.extend(line_tables)
                next_id += len(line_tables)
                continue
        native = _native_tables(page, page_number, next_id, text_blocks)
        if native:
            tables.extend(native)
            next_id += len(native)
            continue
        if not words:
            fallback = _line_table(page, page_number, next_id, text_blocks)
            if fallback:
                tables.append(fallback)
                next_id += 1
    return tables


def table_contains_bbox(table: TableBlock, bbox: BBox) -> bool:
    return _overlap(bbox, table.bbox) >= 0.35 or (
        table.caption_bbox is not None and _overlap(bbox, table.caption_bbox) >= 0.35
    )
