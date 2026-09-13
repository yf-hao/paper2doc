from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

BBox = tuple[float, float, float, float]


@dataclass
class Paragraph:
    id: int
    page: int
    bbox: BBox
    text: str
    column: str = "full"
    region: int = 0
    is_caption: bool = False


@dataclass
class ImageBlock:
    id: int
    page: int
    bbox: BBox
    image_bytes: bytes
    column: str = "full"
    region: int = 0
    parent_paragraph_id: Optional[int] = None
    caption: Optional[str] = None


@dataclass
class ScanInfo:
    is_scan: bool
    pages_without_text: list[int] = field(default_factory=list)
    warning: str | None = None
