from paper2doc.models import ImageBlock
from paper2doc.text_extractor import extract_paragraphs


class FakePage:
    rect = type("Rect", (), {"width": 600, "height": 800})()

    def __init__(self, blocks):
        self.blocks = blocks

    def get_text(self, mode):
        return {"blocks": self.blocks}


def _text_block(bbox, text):
    return {
        "type": 0,
        "bbox": bbox,
        "lines": [{"spans": [{"text": text}]}],
    }


def test_two_column_continuation_merges_left_end_into_right_column():
    document = [
        FakePage(
            [
                _text_block(
                    (50, 100, 250, 130),
                    "The system uses research software and interoperable",
                ),
                _text_block(
                    (350, 50, 550, 80),
                    "scholarly infrastructures [2,12,13].",
                ),
                _text_block((350, 160, 550, 190), "2.1 Design goals"),
            ]
        )
    ]

    paragraphs = extract_paragraphs(
        document,
        remove_page_numbers=False,
        remove_running_headers=False,
    )

    assert [paragraph.text for paragraph in paragraphs] == [
        "The system uses research software and interoperable scholarly infrastructures [2,12,13].",
        "2.1 Design goals",
    ]
    assert paragraphs[0].column == "left"
    assert [(page, column) for page, _bbox, column in paragraphs[0].layout_parts] == [
        (0, "left"),
        (0, "right"),
    ]


def test_page_continuation_merges_when_next_page_starts_mid_sentence():
    document = [
        FakePage([_text_block((50, 740, 550, 770), "The paragraph continues without")]),
        FakePage(
            [
                _text_block((50, 50, 550, 80), "a page boundary."),
                _text_block((50, 220, 550, 250), "New paragraph."),
            ]
        ),
    ]

    paragraphs = extract_paragraphs(
        document,
        remove_page_numbers=False,
        remove_running_headers=False,
    )

    assert [paragraph.text for paragraph in paragraphs] == [
        "The paragraph continues without a page boundary.",
        "New paragraph.",
    ]


def test_page_break_does_not_merge_completed_paragraphs():
    document = [
        FakePage([_text_block((50, 740, 550, 770), "The first paragraph is complete.")]),
        FakePage([_text_block((50, 50, 550, 80), "New paragraph starts here.")]),
    ]

    paragraphs = extract_paragraphs(
        document,
        remove_page_numbers=False,
        remove_running_headers=False,
    )

    assert [paragraph.text for paragraph in paragraphs] == [
        "The first paragraph is complete.",
        "New paragraph starts here.",
    ]


def test_layout_element_between_columns_prevents_paragraph_merge():
    document = [
        FakePage(
            [
                _text_block((50, 100, 250, 130), "The text ends before an illustration"),
                _text_block((350, 100, 550, 130), "and this is separate text."),
            ]
        )
    ]
    image = ImageBlock(1, 0, (350, 40, 550, 90), b"image")

    paragraphs = extract_paragraphs(
        document,
        remove_page_numbers=False,
        remove_running_headers=False,
        images=[image],
    )

    assert [paragraph.text for paragraph in paragraphs] == [
        "The text ends before an illustration",
        "and this is separate text.",
    ]
