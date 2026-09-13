from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from .models import Paragraph


PAGE_NUMBER_RE = re.compile(r"^(?:\d{1,4}|[ivxlcdm]{1,8})$", re.IGNORECASE)


def _number_value(text: str) -> int | None:
    value = text.strip().lower()
    if value.isdigit():
        return int(value)
    roman_values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    if not value or any(character not in roman_values for character in value):
        return None
    total = 0
    previous = 0
    for character in reversed(value):
        current = roman_values[character]
        total += -current if current < previous else current
        previous = current
    return total


def _edge_position(paragraph: Paragraph, page_size: tuple[float, float]) -> tuple[str, float, float] | None:
    page_width, page_height = page_size
    x0, y0, x1, y1 = paragraph.bbox
    if page_width <= 0 or page_height <= 0:
        return None
    if y1 <= page_height * 0.15:
        edge = "top"
    elif y0 >= page_height * 0.85:
        edge = "bottom"
    else:
        return None
    x_center = ((x0 + x1) / 2) / page_width
    y_center = ((y0 + y1) / 2) / page_height
    return edge, round(x_center, 1), round(y_center, 1)


def filter_page_numbers(
    paragraphs: Iterable[Paragraph],
    page_sizes: dict[int, tuple[float, float]],
) -> list[Paragraph]:
    """Remove standalone page numbers from header/footer edge text blocks."""
    paragraphs = list(paragraphs)
    candidates: list[tuple[Paragraph, tuple[str, float, float], int | None]] = []
    for paragraph in paragraphs:
        if not PAGE_NUMBER_RE.fullmatch(paragraph.text.strip()):
            continue
        position = _edge_position(paragraph, page_sizes.get(paragraph.page, (0, 0)))
        if position is not None:
            candidates.append((paragraph, position, _number_value(paragraph.text)))

    repeated_positions = Counter(position for _paragraph, position, _value in candidates)
    page_count = len(page_sizes)
    removed: set[int] = set()
    for paragraph, position, value in candidates:
        edge = position[0]
        recurring = repeated_positions[position] >= 2
        single_page_footer = page_count == 1 and edge == "bottom" and value is not None
        matches_page_index = (
            edge == "bottom"
            and value is not None
            and value in {paragraph.page, paragraph.page + 1}
        )
        if recurring or single_page_footer or matches_page_index:
            removed.add(paragraph.id)
    return [paragraph for paragraph in paragraphs if paragraph.id not in removed]
