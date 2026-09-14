from pathlib import Path

import pytest

from paper2doc.cli import build_parser, main, resolve_output_path


def test_default_output_path():
    path = Path("/papers/example.paper.pdf")
    assert resolve_output_path(path) == Path("/papers/example.paper_bilingual.docx")


def test_no_progress_option_is_available():
    args = build_parser().parse_args(["paper.pdf", "--no-progress"])
    assert args.no_progress is True


def test_keep_running_headers_option_is_available():
    args = build_parser().parse_args(["paper.pdf", "--keep-running-headers"])
    assert args.keep_running_headers is True


def test_batch_size_option_defaults_and_accepts_override():
    parser = build_parser()
    assert parser.parse_args(["paper.pdf"]).batch_size == 7000
    assert parser.parse_args(["paper.pdf", "--batch-size", "5000"]).batch_size == 5000
    assert parser.parse_args(["paper.pdf"]).batch_min_size == 6000
    assert parser.parse_args(["paper.pdf", "--batch-min-size", "4000"]).batch_min_size == 4000


def test_checkpoint_options_are_available():
    args = build_parser().parse_args(
        ["paper.pdf", "--restart", "--keep-checkpoint", "--checkpoint-dir", "/tmp/checkpoints"]
    )
    assert args.restart is True
    assert args.keep_checkpoint is True
    assert args.checkpoint_dir == Path("/tmp/checkpoints")


def test_positional_and_option_input_conflict(tmp_path):
    input_path = tmp_path / "paper.pdf"
    input_path.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(SystemExit) as error:
        main([str(input_path), "--input", str(input_path), "--no-translate"])
    assert error.value.code == 2
