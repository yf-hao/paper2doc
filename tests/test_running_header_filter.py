from paper2doc.models import Paragraph
from paper2doc.running_header_filter import filter_running_headers


def test_repeated_running_headers_are_removed_after_first_page():
    paragraphs = [
        Paragraph(1, 0, (36, 37, 73, 44), "Y. Pérez Vera"),
        Paragraph(2, 1, (37, 37, 74, 44), "Y. Pérez Vera"),
        Paragraph(3, 2, (36, 37, 73, 44), "Y. Pérez Vera"),
        Paragraph(4, 1, (477, 34, 560, 44), "SoftwareX 36 (2026) 103023"),
        Paragraph(5, 2, (477, 34, 560, 44), "SoftwareX 36 (2026) 103023"),
        Paragraph(6, 1, (100, 300, 240, 315), "Y. Pérez Vera"),
        Paragraph(7, 2, (100, 300, 240, 315), "Y. Pérez Vera"),
        Paragraph(8, 2, (477, 34, 560, 44), "SoftwareX 36 (2026) 103023"),
    ]

    filtered = filter_running_headers(
        paragraphs,
        {0: (612, 792), 1: (612, 792), 2: (612, 792)},
    )

    assert [paragraph.id for paragraph in filtered] == [1, 6, 7]


def test_repeated_text_not_at_page_edge_is_preserved():
    paragraphs = [
        Paragraph(1, 0, (100, 300, 240, 315), "Repeated body text"),
        Paragraph(2, 1, (100, 300, 240, 315), "Repeated body text"),
        Paragraph(3, 2, (100, 300, 240, 315), "Repeated body text"),
    ]

    filtered = filter_running_headers(
        paragraphs,
        {0: (612, 792), 1: (612, 792), 2: (612, 792)},
    )

    assert [paragraph.id for paragraph in filtered] == [1, 2, 3]
