from paper2doc.models import ImageBlock, Paragraph
from paper2doc.relation_builder import associate_images


def test_image_attaches_to_nearest_paragraph_above_same_column():
    paragraphs = [
        Paragraph(1, 0, (50, 50, 250, 80), "Fig. 1 is discussed here.", "left"),
        Paragraph(2, 0, (50, 100, 250, 130), "The actual method follows.", "left"),
        Paragraph(3, 0, (300, 100, 500, 130), "A right column reference.", "right"),
    ]
    image = ImageBlock(1, 0, (50, 145, 250, 245), b"image", "left")
    _, result = associate_images(paragraphs, [image])
    assert result[0].parent_paragraph_id == 2


def test_figure_reference_does_not_move_image():
    paragraphs = [
        Paragraph(1, 0, (50, 50, 250, 80), "Text before the figure.", "left"),
        Paragraph(2, 0, (50, 300, 250, 330), "Fig. 9. Caption.", "left", is_caption=True),
    ]
    image = ImageBlock(1, 0, (50, 100, 250, 200), b"image", "left")
    _, result = associate_images(paragraphs, [image])
    assert result[0].parent_paragraph_id == 1
    assert result[0].caption == "Fig. 9. Caption."
