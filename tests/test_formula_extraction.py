from io import BytesIO

from PIL import Image
from docx import Document

from paper2doc.docx_writer import write_docx
from paper2doc.image_extractor import extract_images
from paper2doc.models import ImageBlock, InlineFormula, Paragraph
from paper2doc.text_extractor import extract_paragraphs


class FakeRect:
    x0 = 0
    y0 = 0
    x1 = 600
    y1 = 800
    width = 600
    height = 800


class FakePixmap:
    def tobytes(self, format):
        assert format == "png"
        return b"formula-image"


class FormulaPage:
    rect = FakeRect()

    def __init__(self):
        self.blocks = [
            {
                "type": 0,
                "bbox": (50, 50, 550, 65),
                "lines": [{"spans": [{"text": "Text before the equation."}]}],
            },
            {
                "type": 0,
                "bbox": (150, 85, 175, 110),
                "lines": [{"spans": [{"text": "∑"}]}],
            },
            {
                "type": 0,
                "bbox": (165, 75, 172, 86),
                "lines": [{"spans": [{"text": "s"}]}],
            },
            {
                "type": 0,
                "bbox": (100, 100, 180, 120),
                "lines": [{"spans": [{"text": "ṅi = ni"}]}],
            },
            {
                "type": 0,
                "bbox": (100, 120, 200, 140),
                "lines": [{"spans": [{"text": "rxy,i − ni +"}]}],
            },
            {
                "type": 0,
                "bbox": (160, 140, 240, 155),
                "lines": [{"spans": [{"text": "AijGijnj"}]}],
            },
            {
                "type": 0,
                "bbox": (170, 155, 210, 170),
                "lines": [{"spans": [{"text": "j ≠ i"}]}],
            },
            {
                "type": 0,
                "bbox": (500, 100, 520, 120),
                "lines": [{"spans": [{"text": "(1)"}]}],
            },
            {
                "type": 0,
                "bbox": (50, 220, 550, 235),
                "lines": [{"spans": [{"text": "Text after the equation."}]}],
            },
        ]

    def get_text(self, mode):
        return {"blocks": self.blocks}

    def get_pixmap(self, **kwargs):
        return FakePixmap()


def test_formula_text_is_rendered_once_and_removed_from_paragraphs():
    document = [FormulaPage()]
    images = extract_images(document)

    assert len(images) == 1
    formula = images[0]
    assert formula.is_formula is True
    assert formula.image_bytes == b"formula-image"
    assert formula.bbox[0] == 100
    assert formula.bbox[2] == 520

    paragraphs = extract_paragraphs(
        document,
        remove_page_numbers=False,
        remove_running_headers=False,
        images=images,
    )
    assert [paragraph.text for paragraph in paragraphs] == [
        "Text before the equation.",
        "Text after the equation.",
    ]


def test_block_formulas_stay_separate_from_intervening_prose_and_keep_numbers():
    page = FormulaPage()
    page.blocks = [
        {
            "type": 0,
            "bbox": (100, 100, 180, 120),
            "lines": [{"spans": [{"text": "x = y"}]}],
        },
        {
            "type": 0,
            "bbox": (500, 100, 520, 120),
            "lines": [{"spans": [{"text": "(1)"}]}],
        },
        {
            "type": 0,
            "bbox": (50, 165, 550, 195),
            "lines": [{"spans": [{"text": "where P is the maximum growth rate."}]}],
        },
        {
            "type": 0,
            "bbox": (100, 240, 180, 260),
            "lines": [{"spans": [{"text": "G = exp"}]}],
        },
        {
            "type": 0,
            "bbox": (500, 240, 520, 260),
            "lines": [{"spans": [{"text": "(2)"}]}],
        },
    ]

    formulas = extract_images([page])

    assert len(formulas) == 2
    assert [(formula.bbox[1], formula.bbox[3], formula.bbox[2]) for formula in formulas] == [
        (100, 120, 520),
        (240, 260, 520),
    ]


def test_formula_image_is_not_added_to_translation_units(tmp_path):
    image_data = BytesIO()
    Image.new("RGB", (20, 10), "white").save(image_data, format="PNG")

    class Translator:
        def __init__(self):
            self.units = []

        def translate_batch(self, units):
            self.units.extend(units)
            return {unit_id: f"中文：{text}" for unit_id, text in units}

    translator = Translator()
    output = tmp_path / "formula.docx"
    write_docx(
        [Paragraph(1, 0, (50, 50, 250, 70), "Text before the equation.")],
        [
            ImageBlock(
                1,
                0,
                (50, 80, 150, 120),
                image_data.getvalue(),
                parent_paragraph_id=1,
                is_formula=True,
            )
        ],
        translator,
        output,
        batch_size=1000,
        batch_min_size=1,
    )

    assert translator.units == [("paragraph:1", "Text before the equation.")]
    assert len(Document(output).inline_shapes) == 1


def test_inline_subscript_is_detected_from_span_geometry():
    page = FormulaPage()
    page.blocks = [
        {
            "type": 0,
            "bbox": (50, 100, 250, 120),
            "lines": [
                {
                    "spans": [
                        {"text": "The value ", "bbox": (50, 100, 100, 112), "size": 12},
                        {"text": "u", "bbox": (100, 100, 108, 112), "size": 12},
                        {"text": "x", "bbox": (109, 106, 115, 116), "size": 8},
                        {"text": " is measured.", "bbox": (116, 100, 190, 112), "size": 12},
                    ]
                }
            ],
        }
    ]

    paragraphs = extract_paragraphs(
        [page],
        remove_page_numbers=False,
        remove_running_headers=False,
    )

    assert [paragraph.text for paragraph in paragraphs] == ["The value ux is measured."]
    assert paragraphs[0].inline_formulas == [
        InlineFormula(text="ux", base="u", subscript="x")
    ]


def test_inline_subscript_is_written_as_word_math_not_an_image(tmp_path):
    formula = InlineFormula(text="ux", base="u", subscript="x")
    output = tmp_path / "inline-formula.docx"
    write_docx(
        [Paragraph(1, 0, (0, 0, 200, 20), "The value ux is measured.", inline_formulas=[formula])],
        [],
        lambda text: f"中文：{text}",
        output,
    )

    document = Document(output)
    subscript_elements = list(document._element.body.iter("{http://schemas.openxmlformats.org/officeDocument/2006/math}sSub"))
    assert len(subscript_elements) == 2
    assert len(document.inline_shapes) == 0
