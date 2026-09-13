from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from .models import Paragraph


def _fingerprint(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


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


def filter_running_headers(
    paragraphs: Iterable[Paragraph],
    page_sizes: dict[int, tuple[float, float]],
) -> list[Paragraph]:
    """Remove repeated short text blocks from page headers and footers."""
    paragraphs = list(paragraphs)
    page_count = len(page_sizes)
    candidates: list[tuple[Paragraph, str, tuple[str, float, float]]] = []
    for paragraph in paragraphs:
        if paragraph.is_caption or not paragraph.text.strip() or len(paragraph.text) > 120:
            continue
        position = _edge_position(paragraph, page_sizes.get(paragraph.page, (0, 0)))
        if position is not None:
            candidates.append((paragraph, _fingerprint(paragraph.text), position))

    occurrences: dict[tuple[str, tuple[str, float, float]], set[int]] = defaultdict(set)
    for paragraph, fingerprint, position in candidates:
        occurrences[(fingerprint, position)].add(paragraph.page)

    removed_ids: set[int] = set()
    for paragraph, fingerprint, position in candidates:
        repeated_pages = occurrences[(fingerprint, position)]
        repeated_on_most_pages = len(repeated_pages) > page_count / 2
        repeated_on_many_pages = len(repeated_pages) >= 3
        if (repeated_on_most_pages or repeated_on_many_pages) and paragraph.page > 0:
            removed_ids.add(paragraph.id)
    return [paragraph for paragraph in paragraphs if paragraph.id not in removed_ids]
