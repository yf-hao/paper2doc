from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from paper2doc.docx_writer import write_docx
from paper2doc.models import TableBlock, TableCell
from paper2doc.table_extractor import extract_tables
from paper2doc.text_extractor import extract_paragraphs


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class FakePage:
    rect = type("Rect", (), {"width": 600, "height": 800})()

    def __init__(self):
        self._blocks = [
            {"type": 0, "bbox": (50, 20, 250, 32), "lines": [{"spans": [{"text": "Table 1. Results"}]}]},
            {"type": 0, "bbox": (50, 110, 150, 145), "lines": [
                {"spans": [{"text": "Model"}]},
                {"spans": [{"text": "inter-"}]},
                {"spans": [{"text": "faces"}]},
            ]},
            {"type": 0, "bbox": (220, 110, 320, 125), "lines": [{"spans": [{"text": "Accuracy"}]}]},
            {"type": 0, "bbox": (400, 110, 500, 125), "lines": [{"spans": [{"text": "0.91"}]}]},
            {"type": 0, "bbox": (50, 150, 150, 165), "lines": [{"spans": [{"text": "Baseline"}]}]},
            {"type": 0, "bbox": (220, 150, 320, 165), "lines": [{"spans": [{"text": "Accuracy"}]}]},
            {"type": 0, "bbox": (400, 150, 500, 165), "lines": [{"spans": [{"text": "0.82"}]}]},
            {"type": 0, "bbox": (50, 220, 500, 240), "lines": [{"spans": [{"text": "Ordinary paragraph"}]}]},
        ]

    def get_text(self, mode):
        return {"blocks": self._blocks}

    def get_drawings(self):
        return [
            {"items": [("l", Point(40, 100), Point(520, 100))]},
            {"items": [("l", Point(40, 140), Point(520, 140))]},
            {"items": [("l", Point(40, 180), Point(520, 180))]},
        ]


class WordTablePage:
    rect = type("Rect", (), {"width": 600, "height": 800})()

    def __init__(self):
        self.blocks = [
            {"type": 0, "bbox": (50, 20, 250, 32), "lines": [{"spans": [{"text": "Table 1. Results"}]}]},
        ]
        self.words = [
            (50, 110, 78, 120, "Design", 0, 0, 0),
            (80, 110, 100, 120, "Goal", 0, 0, 1),
            (150, 110, 220, 120, "Motivation", 0, 0, 2),
            (300, 110, 380, 120, "Architectural", 0, 0, 3),
            (382, 110, 450, 120, "Mechanism", 0, 0, 4),
            (50, 130, 120, 140, "Extensibility", 0, 1, 0),
            (150, 130, 190, 140, "Support", 0, 1, 1),
            (192, 130, 245, 140, "inter\u00ad", 0, 1, 2),
            (247, 140, 275, 150, "faces", 0, 1, 3),
            (300, 130, 350, 140, "Standard", 0, 1, 4),
            (50, 150, 100, 160, "Modularity", 0, 2, 0),
            (150, 150, 190, 160, "Separate", 0, 2, 1),
            (300, 150, 350, 160, "Plugin", 0, 2, 2),
        ]

    def get_text(self, mode):
        return self.words if mode == "words" else {"blocks": self.blocks}

    def get_drawings(self):
        return [
            {"items": [("l", Point(40, 100), Point(500, 100))]},
            {"items": [("l", Point(40, 125), Point(500, 125))]},
            {"items": [("l", Point(40, 170), Point(500, 170))]},
        ]


def test_horizontal_rule_table_extracts_grid_and_dehyphenates():
    tables = extract_tables([FakePage()])
    assert len(tables) == 1
    table = tables[0]
    assert (table.rows, table.columns) == (2, 3)
    assert table.vertical_rules is False
    assert table.cells[0].text == "Model interfaces"
    assert table.cells[4].text == "Accuracy"


def test_word_coordinates_extract_three_columns_without_vertical_rules():
    table = extract_tables([WordTablePage()])[0]

    assert (table.rows, table.columns) == (3, 3)
    assert table.vertical_rules is False
    assert table.cells[0].text == "Design Goal"
    assert table.cells[1].text == "Motivation"
    assert table.cells[2].text == "Architectural Mechanism"
    assert table.cells[4].text == "Support interfaces"


def test_table_text_is_not_returned_as_duplicate_paragraphs():
    tables = extract_tables([FakePage()])
    paragraphs = extract_paragraphs([FakePage()], tables=tables, remove_page_numbers=False, remove_running_headers=False)
    assert [paragraph.text for paragraph in paragraphs] == ["Ordinary paragraph"]


class RecordingTranslator:
    def __init__(self):
        self.units = []

    def translate_batch(self, units):
        self.units.extend(units)
        return {unit_id: f"中：{text}" for unit_id, text in units}


def test_table_markers_and_native_english_chinese_grids(tmp_path: Path):
    table = TableBlock(
        id=7,
        page=0,
        bbox=(0, 0, 300, 100),
        rows=2,
        columns=2,
        caption="Table 7. Demo",
        cells=[
            TableCell(0, 0, (0, 0, 100, 50), "Header", is_header=True),
            TableCell(0, 1, (100, 0, 300, 50), "Value", is_header=True),
            TableCell(1, 0, (0, 50, 100, 100), "A"),
            TableCell(1, 1, (100, 50, 300, 100), ""),
        ],
    )
    translator = RecordingTranslator()
    output = tmp_path / "table.docx"
    write_docx([], [], translator, output, tables=[table], batch_size=1000, batch_min_size=1)

    markers = [unit_id for unit_id, _text in translator.units]
    assert markers == [
        "table:7:caption",
        "table:7:r0:c0",
        "table:7:r0:c1",
        "table:7:r1:c0",
    ]
    document = Document(output)
    native_tables = document.tables[-2:]
    assert [[cell.text for cell in row.cells] for row in native_tables[0].rows] == [
        ["Header", "Value"],
        ["A", ""],
    ]
    assert [[cell.text for cell in row.cells] for row in native_tables[1].rows] == [
        ["中：Header", "中：Value"],
        ["中：A", ""],
    ]
    body_children = list(document._element.body)
    english_index = body_children.index(native_tables[0]._element)
    chinese_index = body_children.index(native_tables[1]._element)
    assert chinese_index == english_index + 2
    spacer = body_children[english_index + 1]
    assert spacer.tag == qn("w:p")
    assert "".join(spacer.itertext()).strip() == ""
