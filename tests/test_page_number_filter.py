from paper2doc.models import Paragraph
from paper2doc.page_number_filter import filter_page_numbers


def test_repeated_edge_page_numbers_are_removed_but_body_numbers_remain():
    paragraphs = [
        Paragraph(1, 0, (290, 760, 310, 775), "1"),
        Paragraph(2, 1, (290, 760, 310, 775), "2"),
        Paragraph(3, 2, (290, 760, 310, 775), "3"),
        Paragraph(4, 1, (100, 300, 120, 315), "3"),
    ]

    filtered = filter_page_numbers(
        paragraphs,
        {0: (600, 800), 1: (600, 800), 2: (600, 800)},
    )

    assert [paragraph.id for paragraph in filtered] == [4]


def test_single_page_footer_page_number_is_removed():
    paragraphs = [Paragraph(1, 0, (290, 760, 310, 775), "i")]

    filtered = filter_page_numbers(paragraphs, {0: (600, 800)})

    assert filtered == []


def test_top_page_number_requires_repeated_position():
    paragraphs = [
        Paragraph(1, 0, (290, 20, 310, 35), "1"),
        Paragraph(2, 1, (290, 20, 310, 35), "2"),
    ]

    filtered = filter_page_numbers(
        paragraphs,
        {0: (600, 800), 1: (600, 800)},
    )

    assert filtered == []
