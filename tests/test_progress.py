from io import StringIO

from paper2doc.progress import TerminalProgress


def test_non_tty_progress_reports_start_and_completion():
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress.start(3, "Translating paragraphs")
    progress.update(1)
    progress.update(3)
    progress.finish()

    output = stream.getvalue()
    assert "Translating paragraphs: 0/3 (0.0%)" in output
    assert "Translating paragraphs: 3/3 (100.0%)" in output
    assert output.count("3/3") == 1


def test_progress_can_report_empty_work():
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress.start(0, "Translating paragraphs")

    assert stream.getvalue() == "Translating paragraphs: no items\n"
