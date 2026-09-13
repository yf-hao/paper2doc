from __future__ import annotations

from io import BytesIO

from PIL import Image

from .layout_analyzer import assign_columns, assign_regions
from .models import ImageBlock
from .pdf_api import fitz


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


def extract_images(document: fitz.Document) -> list[ImageBlock]:
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
    assign_columns(images, page_widths)
    assign_regions(images)
    return images
