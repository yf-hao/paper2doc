from __future__ import annotations

from io import BytesIO
import re

from PIL import Image

from .layout_analyzer import assign_columns, assign_regions
from .models import ImageBlock
from .pdf_api import fitz

MATH_SYMBOL_RE = re.compile(r"[∑∫∬∭∮√∞≈≠≤≥±×÷∂∇∈∉⊂⊃→←↔⋅∕−]")
MATH_OPERATOR_RE = re.compile(r"[=+*/^]")
EQUATION_NUMBER_RE = re.compile(r"^\s*[,.;:]?\s*[\(\[]?\d+[a-z]?\)?[\],.;:]?\s*$", re.I)
PROSE_WORD_RE = re.compile(
    r"\b(?:and|are|controls|from|growth|is|maximum|method|rate|the|this|value|where|with)\b",
    re.I,
)


def _block_text(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        value = "".join(span.get("text", "") for span in line.get("spans", []))
        if value.strip():
            lines.append(value.strip())
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _bbox(block: dict) -> tuple[float, float, float, float]:
    return tuple(float(value) for value in block["bbox"])


def _union_bbox(first, second):
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )


def _is_formula_seed(text: str) -> bool:
    if not text or len(text) > 120 or text.endswith((".", "。", "！", "!")):
        return False
    if len(text.split()) > 8 or PROSE_WORD_RE.search(text):
        return False
    if MATH_SYMBOL_RE.search(text):
        return True
    return (
        MATH_OPERATOR_RE.search(text) is not None
        and len(text.split()) <= 10
    )


def _is_formula_fragment(text: str) -> bool:
    if not text or len(text) > 80:
        return False
    if MATH_SYMBOL_RE.search(text) or MATH_OPERATOR_RE.search(text):
        return True
    if not re.fullmatch(r"[\w.,(){}\[\]′″˙\u00ad]+", text, re.UNICODE):
        return False
    if PROSE_WORD_RE.fullmatch(text):
        return False
    return len(text) <= 2 or any(character.isdigit() or character.isupper() for character in text)


def _is_prose_block(text: str) -> bool:
    return len(re.findall(r"\b[\w'-]+\b", text)) >= 4 or PROSE_WORD_RE.search(text) is not None


def _gap(first, second) -> tuple[float, float]:
    horizontal = max(first[0] - second[2], second[0] - first[2], 0)
    vertical = max(first[1] - second[3], second[1] - first[3], 0)
    return horizontal, vertical


def _has_prose_barrier(
    text_blocks: list[dict],
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    top = min(first[3], second[3])
    bottom = max(first[1], second[1])
    left = max(first[0], second[0])
    right = min(first[2], second[2])
    for block in text_blocks:
        text = _block_text(block)
        block_bbox = _bbox(block)
        if not _is_prose_block(text):
            continue
        if block_bbox[3] <= top or block_bbox[1] >= bottom:
            continue
        if block_bbox[2] <= left or block_bbox[0] >= right:
            continue
        return True
    return False


def _formula_groups(page) -> list[tuple[tuple[float, float, float, float], list[dict]]]:
    text_blocks = [
        block
        for block in page.get_text("dict").get("blocks", [])
        if block.get("type") == 0 and _block_text(block)
    ]
    seeds = [block for block in text_blocks if _is_formula_seed(_block_text(block))]
    groups: list[tuple[tuple[float, float, float, float], list[dict]]] = []
    remaining = list(seeds)
    while remaining:
        members = [remaining.pop(0)]
        group_bbox = _bbox(members[0])
        changed = True
        while changed:
            changed = False
            for block in list(remaining):
                block_bbox = _bbox(block)
                horizontal, vertical = _gap(group_bbox, block_bbox)
                if (
                    horizontal <= 40
                    and vertical <= 32
                    and not _has_prose_barrier(text_blocks, group_bbox, block_bbox)
                ):
                    members.append(block)
                    group_bbox = _union_bbox(group_bbox, block_bbox)
                    remaining.remove(block)
                    changed = True
        groups.append((group_bbox, members))

    for index, (group_bbox, members) in enumerate(groups):
        for block in text_blocks:
            if block in members:
                continue
            text = _block_text(block)
            block_bbox = _bbox(block)
            horizontal, vertical = _gap(group_bbox, block_bbox)
            if (
                _is_formula_fragment(text)
                and horizontal <= 40
                and vertical <= 32
                and not _has_prose_barrier(text_blocks, group_bbox, block_bbox)
            ):
                members.append(block)
                group_bbox = _union_bbox(group_bbox, block_bbox)
        groups[index] = (group_bbox, members)

    assigned_numbers: set[int] = set()
    for block in text_blocks:
        text = _block_text(block)
        if not EQUATION_NUMBER_RE.fullmatch(text):
            continue
        block_bbox = _bbox(block)
        candidates = []
        for index, (group_bbox, members) in enumerate(groups):
            if block in members:
                continue
            vertical = max(group_bbox[1] - block_bbox[3], block_bbox[1] - group_bbox[3], 0)
            horizontal = max(block_bbox[0] - group_bbox[2], group_bbox[0] - block_bbox[2], 0)
            if vertical <= 14 and horizontal <= max(page.rect.width * 0.65, 80):
                candidates.append((vertical + horizontal * 0.01, index))
        if not candidates:
            continue
        _score, index = min(candidates)
        if index in assigned_numbers:
            continue
        group_bbox, members = groups[index]
        members.append(block)
        groups[index] = (_union_bbox(group_bbox, block_bbox), members)
        assigned_numbers.add(index)
    return groups


def _render_formula(page, bbox) -> bytes:
    page_rect = page.rect
    padding = 2
    clip = fitz.Rect(
        max(page_rect.x0, bbox[0] - padding),
        max(page_rect.y0, bbox[1] - padding),
        min(page_rect.x1, bbox[2] + padding),
        min(page_rect.y1, bbox[3] + padding),
    )
    return page.get_pixmap(
        clip=clip,
        matrix=fitz.Matrix(2.5, 2.5),
        alpha=False,
    ).tobytes("png")


def _overlap(first, second) -> float:
    width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    area = width * height
    source = max((first[2] - first[0]) * (first[3] - first[1]), 1.0)
    return area / source


def _extract_formula_images(
    document: fitz.Document,
    next_id: int,
    exclude_bboxes: dict[int, list[tuple[float, float, float, float]]] | None = None,
) -> list[ImageBlock]:
    formulas: list[ImageBlock] = []
    formula_id = next_id
    for page_number, page in enumerate(document):
        for bbox, _members in _formula_groups(page):
            if any(
                _overlap(bbox, excluded) >= 0.5
                for excluded in (exclude_bboxes or {}).get(page_number, [])
            ):
                continue
            formulas.append(
                ImageBlock(
                    id=formula_id,
                    page=page_number,
                    bbox=bbox,
                    image_bytes=_render_formula(page, bbox),
                    is_formula=True,
                )
            )
            formula_id += 1
    return formulas


def _docx_compatible(data: bytes) -> bytes:
    """Normalize uncommon PDF JPEG encodings to a format Word accepts."""
    try:
        image = Image.open(BytesIO(data))
        if image.format in {"PNG", "JPEG", "GIF", "BMP", "TIFF"} and not (
            image.format == "JPEG" and data[2:4] == b"\xff\xee"
        ):
            return data
        converted = BytesIO()
        image.convert("RGB").save(converted, format="PNG")
        return converted.getvalue()
    except Exception:
        return data


def extract_images(
    document: fitz.Document,
    exclude_bboxes: dict[int, list[tuple[float, float, float, float]]] | None = None,
) -> list[ImageBlock]:
    images: list[ImageBlock] = []
    page_widths = {}
    image_id = 1
    for page_number, page in enumerate(document):
        page_widths[page_number] = page.rect.width
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 1:
                continue
            data = block.get("image")
            if not data and block.get("xref"):
                data = document.extract_image(block["xref"]).get("image")
            if not data:
                continue
            images.append(
                ImageBlock(
                    id=image_id,
                    page=page_number,
                    bbox=tuple(float(value) for value in block["bbox"]),
                    image_bytes=_docx_compatible(data),
                )
            )
            image_id += 1
    images.extend(_extract_formula_images(document, image_id, exclude_bboxes))
    assign_columns(images, page_widths)
    assign_regions(images)
    return images
