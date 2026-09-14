from __future__ import annotations

import re
from collections.abc import Iterable

from .models import BBox, ImageBlock, Paragraph

CAPTION_RE = re.compile(r"^\s*(?:fig(?:ure)?|table|图|表)\s*[\w.-]*\s*[:.]?", re.I)


Location = tuple[int, BBox, str]


def _locations(paragraph: Paragraph) -> list[Location]:
    if paragraph.layout_parts:
        return paragraph.layout_parts
    return [(paragraph.page, paragraph.bbox, paragraph.column)]


def _distance_to_location(image: ImageBlock, location: Location) -> float:
    _page, bbox, _column = location
    return abs(image.bbox[1] - bbox[3])


def associate_images(paragraphs: Iterable[Paragraph], images: Iterable[ImageBlock]) -> tuple[list[Paragraph], list[ImageBlock]]:
    """Associate images using geometry only; figure references never affect placement."""
    paragraphs = list(paragraphs)
    images = list(images)
    captions = [item for item in paragraphs if item.is_caption or CAPTION_RE.match(item.text)]
    for caption in captions:
        caption.is_caption = True
    for caption in captions:
        candidates = [
            image for image in images
            if image.page == caption.page
            and image.bbox[3] <= caption.bbox[1] + 2
            and not image.caption
            and (caption.column == image.column or image.column == "full" or caption.column == "full")
        ]
        if candidates:
            image = min(candidates, key=lambda item: abs(item.bbox[3] - caption.bbox[1]))
            image.caption = caption.text

    for image in images:
        candidates = [
            paragraph for paragraph in paragraphs
            if not paragraph.is_caption
            and any(page == image.page for page, _bbox, _column in _locations(paragraph))
        ]
        same_column = [
            item for item in candidates
            if image.column == "full"
            or any(
                page == image.page and (column == image.column or column == "full")
                for page, _bbox, column in _locations(item)
            )
        ]
        above = [
            item for item in same_column
            if any(
                page == image.page and bbox[3] <= image.bbox[1] + 2
                for page, bbox, _column in _locations(item)
            )
        ]
        if above:
            chosen = min(
                above,
                key=lambda item: min(
                    _distance_to_location(image, location)
                    for location in _locations(item)
                    if location[0] == image.page and location[1][3] <= image.bbox[1] + 2
                ),
            )
        elif same_column:
            chosen = min(
                same_column,
                key=lambda item: min(
                    _distance_to_location(image, location)
                    for location in _locations(item)
                    if location[0] == image.page
                ),
            )
        elif candidates:
            above_any = [
                item for item in candidates
                if any(
                    page == image.page and bbox[3] <= image.bbox[1] + 2
                    for page, bbox, _column in _locations(item)
                )
            ]
            chosen = min(
                above_any or candidates,
                key=lambda item: min(
                    _distance_to_location(image, location)
                    for location in _locations(item)
                    if location[0] == image.page
                ),
            )
        else:
            chosen = None
        image.parent_paragraph_id = chosen.id if chosen else None
    return paragraphs, images
