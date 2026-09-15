from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

BBox = tuple[float, float, float, float]


@dataclass
class InlineFormula:
    text: str
    base: str
    subscript: str | None = None
    superscript: str | None = None


@dataclass
class Paragraph:
    id: int
    page: int
    bbox: BBox
    text: str
    column: str = "full"
    region: int = 0
    is_caption: bool = False
    layout_parts: list[tuple[int, BBox, str]] = field(default_factory=list, repr=False)
    inline_formulas: list[InlineFormula] = field(default_factory=list, repr=False)


@dataclass
class TableCell:
    row: int
    column: int
    bbox: BBox
    text: str = ""
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False


@dataclass
class TableBlock:
    id: int
    page: int
    bbox: BBox
    rows: int
    columns: int
    cells: list[TableCell] = field(default_factory=list)
    caption: str | None = None
    caption_bbox: BBox | None = None
    column: str = "full"
    region: int = 0
    horizontal_rules: bool = False
    vertical_rules: bool = False
    fallback_image_bytes: bytes | None = None


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
    is_formula: bool = False


@dataclass
class ScanInfo:
    is_scan: bool
    pages_without_text: list[int] = field(default_factory=list)
    warning: str | None = None
