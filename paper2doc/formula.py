from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zipfile import BadZipFile, ZipFile

from docx.oxml import parse_xml
from lxml.etree import XMLSyntaxError

FORMULA_NUMBER_RE = re.compile(r"^\(?\d+[a-z]?\)?[,.]?$", re.I)
COMBINING_DOT_RE = re.compile(r"([A-Za-z])\u0307")
UNICODE_LATEX = {
    "∑": r"\sum",
    "∫": r"\int",
    "∬": r"\iint",
    "∭": r"\iiint",
    "∮": r"\oint",
    "√": r"\sqrt",
    "∞": r"\infty",
    "≈": r"\approx",
    "≠": r"\ne",
    "≤": r"\le",
    "≥": r"\ge",
    "±": r"\pm",
    "×": r"\times",
    "÷": r"\div",
    "∂": r"\partial",
    "∇": r"\nabla",
    "∈": r"\in",
    "∉": r"\notin",
    "⊂": r"\subset",
    "⊃": r"\supset",
    "→": r"\to",
    "←": r"\leftarrow",
    "↔": r"\leftrightarrow",
    "⋅": r"\cdot",
    "∕": "/",
    "−": "-",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "θ": r"\theta",
    "λ": r"\lambda",
    "μ": r"\mu",
    "π": r"\pi",
    "σ": r"\sigma",
    "φ": r"\phi",
    "ω": r"\omega",
}


def _block_text(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        value = "".join(span.get("text", "") for span in line.get("spans", []))
        if value.strip():
            lines.append(value.strip())
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _to_latex_piece(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = COMBINING_DOT_RE.sub(r"\\dot{\1}", text)
    for source, target in UNICODE_LATEX.items():
        text = text.replace(source, f" {target} ")
    text = text.replace("˙", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def formula_to_latex(members: list[dict]) -> str | None:
    """Convert extracted formula text fragments to a conservative LaTeX string."""
    pieces: list[str] = []
    equation_number: str | None = None
    seen: set[tuple[tuple[float, float, float, float], str]] = set()
    for block in sorted(
        members,
        key=lambda item: (
            float(item["bbox"][1]),
            float(item["bbox"][0]),
        ),
    ):
        text = _block_text(block)
        if not text:
            continue
        if FORMULA_NUMBER_RE.fullmatch(text):
            equation_number = text.rstrip(".,")
            continue
        key = (tuple(float(value) for value in block["bbox"]), text)
        if key in seen:
            continue
        seen.add(key)
        converted = _to_latex_piece(text)
        if converted:
            pieces.append(converted)
    value = re.sub(r"\s+", " ", " ".join(pieces)).strip()
    if not value or not any(character in value for character in "=+*/^\\"):
        return None
    if len(value) > 500 or len(value.split()) > 80:
        return None
    if equation_number:
        value = f"{value} \\qquad {equation_number}"
    return rf"\displaystyle {value}"


def latex_to_omml(latex: str):
    """Use Pandoc to convert LaTeX into a Word OMML element when available."""
    pandoc = shutil.which("pandoc")
    if not pandoc:
        return None
    with tempfile.TemporaryDirectory(prefix="paper2doc-latex-") as directory:
        output = Path(directory) / "formula.docx"
        try:
            result = subprocess.run(
                [
                    pandoc,
                    "--from=latex",
                    "--to=docx",
                    "--output",
                    str(output),
                ],
                input=f"\\[{latex}\\]\n",
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0 or not output.is_file():
            return None
        try:
            with ZipFile(output) as archive:
                xml = archive.read("word/document.xml")
            root = parse_xml(xml)
        except (BadZipFile, KeyError, ValueError, XMLSyntaxError):
            return None
    for element in root.iter():
        if element.tag.endswith("}oMathPara"):
            return element
    return None
