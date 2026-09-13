from __future__ import annotations

import re
from collections.abc import Iterable

from .models import ImageBlock, Paragraph

CAPTION_RE = re.compile(r"^\s*(?:fig(?:ure)?|table|图|表)\s*[\w.-]*\s*[:.]?", re.I)


def _distance(image: ImageBlock, paragraph: Paragraph) -> float:
    return abs(image.bbox[1] - paragraph.bbox[3])


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
            if not paragraph.is_caption and paragraph.page == image.page
        ]
        same_column = [item for item in candidates if item.column == image.column or image.column == "full"]
        above = [item for item in same_column if item.bbox[3] <= image.bbox[1] + 2]
        if above:
            chosen = min(above, key=lambda item: _distance(image, item))
        elif same_column:
            chosen = min(same_column, key=lambda item: _distance(image, item))
        elif candidates:
            above_any = [item for item in candidates if item.bbox[3] <= image.bbox[1] + 2]
            chosen = min(above_any or candidates, key=lambda item: _distance(image, item))
        else:
            chosen = None
        image.parent_paragraph_id = chosen.id if chosen else None
    return paragraphs, images
