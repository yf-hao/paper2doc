from __future__ import annotations

from collections.abc import Iterable

from .models import BBox, ImageBlock, Paragraph


def classify_column(bbox: BBox, page_width: float) -> str:
    """Classify an element as left, right, or full-width."""
    x0, _y0, x1, _y1 = bbox
    middle = page_width / 2
    width = x1 - x0
    if x0 < middle < x1 and width > page_width * 0.6:
        return "full"
    if x1 <= middle:
        return "left"
    if x0 >= middle:
        return "right"
    return "full"


def assign_columns(elements: Iterable[Paragraph | ImageBlock], page_widths: dict[int, float]):
    """Assign columns in place and return the elements."""
    elements = list(elements)
    for element in elements:
        element.column = classify_column(element.bbox, page_widths[element.page])
    return elements


def assign_regions(elements: Iterable[Paragraph | ImageBlock]) -> list:
    """Assign a simple region number split by full-width elements on each page."""
    elements = list(elements)
    for page in sorted({item.page for item in elements}):
        page_items = [item for item in elements if item.page == page]
        full_items = sorted(
            (item for item in page_items if item.column == "full"),
            key=lambda item: item.bbox[1],
        )
        for item in page_items:
            region = 0
            for full_item in full_items:
                if full_item.bbox[1] < item.bbox[1]:
                    region += 1
            item.region = region
    return elements


def reading_order(elements: Iterable[Paragraph | ImageBlock]) -> list:
    """Return normal reading order: full items, then left column, then right column."""
    groups: dict[tuple[int, int], list] = {}
    for item in elements:
        groups.setdefault((item.page, item.region), []).append(item)
    ordered = []
    for key in sorted(groups):
        group = groups[key]
        for column in ("full", "left", "right"):
            ordered.extend(
                sorted(
                    (item for item in group if item.column == column),
                    key=lambda item: (item.bbox[1], item.bbox[0]),
                )
            )
    return ordered
