from __future__ import annotations

try:
    import pymupdf as fitz
except ModuleNotFoundError:
    import fitz

__all__ = ["fitz"]
