"""The app's behaviour around the conversion: what it asks, and what it does
with the answers. Anything that would otherwise need a person at a keyboard is
driven by feeding lines to input().
"""

from __future__ import annotations

import argparse

import pytest
from PIL import Image

from image_convertor import cli
from image_convertor.converter import DEFAULT_THRESHOLD, Size


@pytest.fixture
def answers(monkeypatch):
    """Queue up what the user types. Each call to input() takes the next line."""

    def queue(*lines: str) -> None:
        remaining = list(lines)
        monkeypatch.setattr(cli, "ask", lambda prompt="": remaining.pop(0))

    return queue


@pytest.fixture
def images(tmp_path, monkeypatch):
    """An input folder beside the app, with two images of different shapes."""
    folder = tmp_path / cli.INPUT_NAME
    folder.mkdir()
    Image.new("RGBA", (20, 16), (0, 0, 0, 0)).save(folder / "clear.png")
    Image.new("RGB", (8, 8), (0, 0, 0)).save(folder / "black.png")
    monkeypatch.setattr(cli, "base_folder", lambda: tmp_path)
    return tmp_path


def output_files(base):
    return sorted(path.name for path in (base / cli.OUTPUT_NAME).iterdir())


# --- the size question ---------------------------------------------------

def test_enter_at_the_size_question_means_no_resizing(answers):
    answers("")
    assert cli.ask_size() is None


def test_the_size_question_asks_again_after_a_bad_answer(answers, capsys):
    answers("wide", "10x10")

    assert cli.ask_size() == Size(10, 10)
    assert "Expected" in capsys.readouterr().out


# --- the mode question ---------------------------------------------------

@pytest.mark.parametrize("answer", ["", "1", "dither", "D"])
def test_choosing_dither_gives_no_threshold(answers, answer):
    answers(answer)
    assert cli.ask_threshold_mode() is None


@pytest.mark.parametrize("answer", ["2", "hard cut", "HARD-CUT"])
def test_choosing_hard_cut_asks_where_to_cut(answers, answer):
    answers(answer, "200")
    assert cli.ask_threshold_mode() == 200


def test_enter_at_the_cut_takes_the_middle(answers):
    answers("2", "")
    assert cli.ask_threshold_mode() == DEFAULT_THRESHOLD


def test_the_mode_question_asks_again_after_a_bad_answer(answers, capsys):
    answers("maybe", "1")

    assert cli.ask_threshold_mode() is None
    assert "Enter 1 or 2" in capsys.readouterr().out


@pytest.mark.parametrize("bad", ["300", "-1", "half"])
def test_the_cut_asks_again_after_a_bad_level(answers, bad):
    answers("2", bad, "64")
    assert cli.ask_threshold_mode() == 64


# --- the flags that stand in for the questions ---------------------------

def resolve(**flags):
    return cli.resolve_threshold(
        argparse.Namespace(**{"mode": None, "threshold": None, **flags})
    )


def test_mode_flags_answer_the_question_without_asking(monkeypatch):
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert resolve(mode="dither") is None
    assert resolve(mode="hard-cut") == DEFAULT_THRESHOLD
    assert resolve(mode="hard-cut", threshold=90) == 90
    assert resolve(threshold=90) == 90  # a threshold on its own implies a cut


def test_a_threshold_with_dither_is_refused(capsys):
    assert cli.main(["--mode", "dither", "--threshold", "90"]) == 1
    assert "does not go with" in capsys.readouterr().out


@pytest.mark.parametrize("threshold", ["-1", "256"])
def test_an_out_of_range_threshold_is_refused(threshold, capsys):
    assert cli.main(["--threshold", threshold]) == 1
    assert "between 0 and 255" in capsys.readouterr().out


# --- end to end ----------------------------------------------------------

def test_a_full_run_converts_the_input_folder(images, answers):
    answers("10x10", "2", "")  # size, hard cut, default level

    assert cli.main([]) == 0
    assert output_files(images) == ["black.bmp", "clear.bmp"]

    with Image.open(images / cli.OUTPUT_NAME / "clear.bmp") as result:
        assert result.mode == "1"
        assert result.size == (10, 10)


def test_flags_run_it_without_any_questions(images, monkeypatch):
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert cli.main(["--size", "16x16", "--mode", "dither"]) == 0
    with Image.open(images / cli.OUTPUT_NAME / "black.bmp") as result:
        assert result.size == (16, 16)


def test_an_empty_size_flag_means_no_resizing(images, monkeypatch):
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert cli.main(["--size", "", "--mode", "dither"]) == 0
    with Image.open(images / cli.OUTPUT_NAME / "clear.bmp") as result:
        assert result.size == (20, 16)


def test_a_missing_input_folder_asks_for_a_path(tmp_path, monkeypatch, answers):
    """No input\\ beside the app is the normal first run, not an error."""
    elsewhere = tmp_path / "pictures"
    elsewhere.mkdir()
    Image.new("RGB", (4, 4)).save(elsewhere / "one.png")

    base = tmp_path / "app"
    base.mkdir()
    monkeypatch.setattr(cli, "base_folder", lambda: base)
    answers(f'"{elsewhere}"', "", "1")  # quoted path, no resize, dither

    assert cli.main([]) == 0
    assert output_files(base) == ["one.bmp"]


def test_a_bad_path_is_asked_about_again(tmp_path, monkeypatch, answers, capsys):
    elsewhere = tmp_path / "pictures"
    elsewhere.mkdir()
    Image.new("RGB", (4, 4)).save(elsewhere / "one.png")

    empty = tmp_path / "empty"
    empty.mkdir()
    base = tmp_path / "app"
    base.mkdir()
    monkeypatch.setattr(cli, "base_folder", lambda: base)
    answers("D:\\nope\\nope", str(empty), str(elsewhere), "", "1")

    assert cli.main([]) == 0
    printed = capsys.readouterr().out
    assert "Not a folder" in printed
    assert "No images in" in printed


def test_answering_nothing_to_the_path_quits(tmp_path, monkeypatch, answers):
    base = tmp_path / "app"
    base.mkdir()
    monkeypatch.setattr(cli, "base_folder", lambda: base)
    answers("")

    with pytest.raises(SystemExit) as quit_:
        cli.main([])
    assert quit_.value.code == 0


def test_an_empty_input_folder_is_reported(images, monkeypatch, capsys):
    empty = images / "empty"
    empty.mkdir()

    assert cli.main(["--input", str(empty), "--size", "", "--mode", "dither"]) == 1
    assert "No images to convert" in capsys.readouterr().out


def test_an_unreadable_file_does_not_stop_the_batch(images, capsys):
    (images / cli.INPUT_NAME / "broken.png").write_bytes(b"not a png")

    code = cli.main(["--size", "", "--mode", "dither"])

    printed = capsys.readouterr().out
    assert code == 1  # the run is reported as failed ...
    assert "FAILED  broken.png" in printed
    assert "2 converted, 1 failed" in printed  # ... but the good ones are done
    assert output_files(images) == ["black.bmp", "clear.bmp"]


def test_the_input_flag_overrides_the_input_folder(images, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    Image.new("RGB", (4, 4)).save(elsewhere / "only.png")
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert cli.main(["--input", str(elsewhere), "--size", "", "--mode", "dither"]) == 0
    assert output_files(images) == ["only.bmp"]
