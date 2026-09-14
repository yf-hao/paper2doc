from pathlib import Path

import pytest

from paper2doc.checkpoint import CheckpointStore
from paper2doc.docx_writer import write_docx
from paper2doc.models import Paragraph


class FailingBatchTranslator:
    def __init__(self):
        self.batch_calls = []

    def translate_batch(self, units):
        self.batch_calls.append(units)
        if len(self.batch_calls) > 1:
            raise RuntimeError("translation interrupted")
        return {unit_id: f"中文：{text}" for unit_id, text in units}

    def translate(self, text):
        raise RuntimeError("translation interrupted")


class RecordingBatchTranslator:
    def __init__(self):
        self.batch_calls = []

    def translate_batch(self, units):
        self.batch_calls.append(units)
        return {unit_id: f"中文：{text}" for unit_id, text in units}


class RecordingProgress:
    def __init__(self):
        self.stages = []

    def stage(self, message):
        self.stages.append(message)

    def start(self, total, description):
        pass

    def update(self, completed):
        pass

    def finish(self):
        pass

    def fail(self):
        pass


def _settings():
    return {
        "batch_size": 5,
        "batch_min_size": 1,
        "remove_page_numbers": True,
        "remove_running_headers": True,
        "model": "test-model",
        "base_url": "https://example.test/v1",
    }


def test_checkpoint_round_trip_and_source_validation(tmp_path: Path):
    input_path = tmp_path / "paper.pdf"
    input_path.write_bytes(b"fake pdf")
    store = CheckpointStore(input_path, _settings(), directory=tmp_path / "checkpoints")
    units = [("paragraph:1", "hello")]

    store.record(units, {"paragraph:1": "你好"})

    restored = CheckpointStore(input_path, _settings(), directory=tmp_path / "checkpoints")
    assert restored.restored_translations(units) == {"paragraph:1": "你好"}
    assert restored.restored_translations([("paragraph:1", "changed")]) == {}


def test_resume_skips_completed_batch_and_deletes_checkpoint_after_docx(tmp_path: Path):
    input_path = tmp_path / "paper.pdf"
    input_path.write_bytes(b"fake pdf")
    checkpoint_dir = tmp_path / "checkpoints"
    paragraphs = [
        Paragraph(1, 0, (0, 0, 100, 20), "12345"),
        Paragraph(2, 0, (0, 30, 100, 50), "67890"),
    ]
    first_store = CheckpointStore(input_path, _settings(), directory=checkpoint_dir)
    first_translator = FailingBatchTranslator()

    with pytest.raises(RuntimeError, match="translation interrupted"):
        write_docx(
            paragraphs,
            [],
            first_translator,
            tmp_path / "first.docx",
            batch_size=5,
            batch_min_size=1,
            checkpoint=first_store,
        )

    assert first_store.path.is_file()
    assert len(first_translator.batch_calls) == 4

    second_store = CheckpointStore(input_path, _settings(), directory=checkpoint_dir)
    second_translator = RecordingBatchTranslator()
    progress = RecordingProgress()
    output = tmp_path / "resumed.docx"
    write_docx(
        paragraphs,
        [],
        second_translator,
        output,
        batch_size=5,
        batch_min_size=1,
        checkpoint=second_store,
        progress=progress,
    )

    assert second_translator.batch_calls == [[("paragraph:2", "67890")]]
    assert output.is_file()
    assert not second_store.path.exists()
    assert progress.stages[-1] == f"Checkpoint removed: {second_store.path}"
