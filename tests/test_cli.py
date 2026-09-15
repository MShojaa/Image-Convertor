"""The app's behaviour around the conversion: what it asks, and what it does
with the answers. Anything that would otherwise need a person at a keyboard is
driven by feeding lines to input().
"""

from __future__ import annotations

import argparse

import pytest
from PIL import Image

from image_convertor import cli
from image_convertor.converter import Size
from image_convertor.effects import DEFAULT_THRESHOLD, Monochrome


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
    """resolve_effects, with every flag defaulted to absent."""
    return cli.resolve_effects(
        argparse.Namespace(**{"mode": None, "threshold": None, "effect": None, **flags})
    )


def test_mode_flags_answer_the_question_without_asking(monkeypatch):
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert resolve(mode="dither") == (Monochrome(None),)
    assert resolve(mode="hard-cut") == (Monochrome(DEFAULT_THRESHOLD),)
    assert resolve(mode="hard-cut", threshold=90) == (Monochrome(90),)
    # a threshold on its own implies a cut
    assert resolve(threshold=90) == (Monochrome(90),)


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
    assert output_files(images) == ["black.png", "clear.png"]

    with Image.open(images / cli.OUTPUT_NAME / "clear.png") as result:
        assert result.mode == "1"
        assert result.size == (10, 10)


def test_flags_run_it_without_any_questions(images, monkeypatch):
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert cli.main(["--size", "16x16", "--mode", "dither"]) == 0
    with Image.open(images / cli.OUTPUT_NAME / "black.png") as result:
        assert result.size == (16, 16)


def test_an_empty_size_flag_means_no_resizing(images, monkeypatch):
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert cli.main(["--size", "", "--mode", "dither"]) == 0
    with Image.open(images / cli.OUTPUT_NAME / "clear.png") as result:
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
    assert output_files(base) == ["one.png"]


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
    assert output_files(images) == ["black.png", "clear.png"]


def test_the_input_flag_overrides_the_input_folder(images, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    Image.new("RGB", (4, 4)).save(elsewhere / "only.png")
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert cli.main(["--input", str(elsewhere), "--size", "", "--mode", "dither"]) == 0
    assert output_files(images) == ["only.png"]


# --- the "could not shrink" warning --------------------------------------

def make_input(base, sizes):
    """An input folder holding one black image per name -> size given."""
    folder = base / cli.INPUT_NAME
    folder.mkdir(exist_ok=True)
    for name, size in sizes.items():
        Image.new("RGB", size, (0, 0, 0)).save(folder / name)
    return base


def convert_at(base, size, monkeypatch):
    monkeypatch.setattr(cli, "base_folder", lambda: base)
    code = cli.main(["--size", size, "--mode", "dither"])
    assert code == 0
    return code


def test_an_image_already_inside_the_box_warns(tmp_path, monkeypatch, capsys):
    make_input(tmp_path, {"small.png": (4, 4)})
    convert_at(tmp_path, "10x10", monkeypatch)

    printed = capsys.readouterr().out
    assert "WARNING" in printed
    assert "already 4x4" in printed
    assert "not shrunk" in printed


def test_nothing_shrinkable_says_so_at_the_end(tmp_path, monkeypatch, capsys):
    make_input(tmp_path, {"a.png": (4, 4), "b.png": (8, 2)})
    convert_at(tmp_path, "10x10", monkeypatch)

    assert "WARNING: nothing was shrunk" in capsys.readouterr().out


def test_some_shrinkable_names_the_ones_that_were_not(tmp_path, monkeypatch, capsys):
    make_input(tmp_path, {"big.png": (40, 40), "small.png": (4, 4)})
    convert_at(tmp_path, "10x10", monkeypatch)

    printed = capsys.readouterr().out
    assert "WARNING: 1 of 2 image(s) could not be shrunk" in printed
    assert "small.png" in printed
    assert "nothing was shrunk" not in printed


def test_a_long_list_of_warnings_is_cut_short(tmp_path, monkeypatch, capsys):
    sizes = {f"small{index}.png": (4, 4) for index in range(8)}
    sizes["big.png"] = (40, 40)
    make_input(tmp_path, sizes)
    convert_at(tmp_path, "10x10", monkeypatch)

    summary = capsys.readouterr().out.rsplit("WARNING:", 1)[1]
    assert "8 of 9 image(s)" in summary
    assert "and 3 more" in summary


def test_shrinking_everything_warns_about_nothing(tmp_path, monkeypatch, capsys):
    make_input(tmp_path, {"a.png": (40, 40), "b.png": (20, 16)})
    convert_at(tmp_path, "10x10", monkeypatch)

    assert "WARNING" not in capsys.readouterr().out


def test_an_exact_fit_warns_about_nothing(tmp_path, monkeypatch, capsys):
    make_input(tmp_path, {"a.png": (10, 10)})
    convert_at(tmp_path, "10x10", monkeypatch)

    assert "WARNING" not in capsys.readouterr().out


def test_no_resizing_warns_about_nothing(tmp_path, monkeypatch, capsys):
    """With no box there is no shrinking to fail at."""
    make_input(tmp_path, {"a.png": (4, 4), "b.png": (40, 40)})
    convert_at(tmp_path, "", monkeypatch)

    assert "WARNING" not in capsys.readouterr().out


# --- the --effect flag ---------------------------------------------------

def test_the_effect_flag_is_repeatable(monkeypatch):
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert resolve(effect=["monochrome:200"]) == (Monochrome(200),)


def test_effect_none_means_convert_as_is(monkeypatch):
    """An absent flag already means "ask me", so no effects has to be spelled."""
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert resolve(effect=["none"]) == ()


def test_the_effect_flag_wins_over_the_older_ones():
    assert resolve(effect=["monochrome:90"], mode="dither") == (Monochrome(90),)


def test_a_bad_effect_is_refused_with_the_known_names(images, capsys):
    assert cli.main(["--size", "", "--effect", "sepia"]) == 1

    printed = capsys.readouterr().out
    assert "sepia" in printed
    assert "monochrome" in printed


def test_effects_are_printed_before_the_run(images, monkeypatch, capsys):
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    cli.main(["--size", "", "--effect", "monochrome:200"])

    assert "Effects: monochrome:200" in capsys.readouterr().out


def test_no_effects_still_writes_the_files(images, monkeypatch):
    """A run with nothing to apply is a copy through the resize, not an error."""
    monkeypatch.setattr(cli, "ask", lambda prompt="": pytest.fail("should not ask"))

    assert cli.main(["--size", "8x8", "--effect", "none"]) == 0
    assert output_files(images) == ["black.png", "clear.png"]


# --- the --format flag ---------------------------------------------------

def test_the_output_is_named_for_the_input_format_by_default(tmp_path, monkeypatch):
    """A png in gives a png out; a bmp in gives a bmp out."""
    make_input(tmp_path, {"a.png": (8, 8)})
    Image.new("RGB", (8, 8)).save(tmp_path / cli.INPUT_NAME / "b.bmp")
    monkeypatch.setattr(cli, "base_folder", lambda: tmp_path)

    assert cli.main(["--size", "", "--effect", "none"]) == 0
    assert output_files(tmp_path) == ["a.png", "b.bmp"]


def test_the_format_flag_writes_one_format_for_everything(tmp_path, monkeypatch):
    make_input(tmp_path, {"a.png": (8, 8)})
    Image.new("RGB", (8, 8)).save(tmp_path / cli.INPUT_NAME / "b.bmp")
    monkeypatch.setattr(cli, "base_folder", lambda: tmp_path)

    assert cli.main(["--size", "", "--effect", "none", "--format", "gif"]) == 0
    assert output_files(tmp_path) == ["a.gif", "b.gif"]


def test_an_unknown_format_is_refused_before_anything_is_written(tmp_path, monkeypatch, capsys):
    make_input(tmp_path, {"a.png": (8, 8)})
    monkeypatch.setattr(cli, "base_folder", lambda: tmp_path)

    assert cli.main(["--size", "", "--effect", "none", "--format", "heic"]) == 1

    assert "heic" in capsys.readouterr().out
    assert not (tmp_path / cli.OUTPUT_NAME).exists()


def test_monochrome_into_jpeg_fails_that_file_and_says_why(tmp_path, monkeypatch, capsys):
    """The batch carries on -- one refused pairing is not a reason to stop."""
    folder = tmp_path / cli.INPUT_NAME
    folder.mkdir()
    Image.new("RGB", (8, 8)).save(folder / "photo.jpg")
    Image.new("RGB", (8, 8)).save(folder / "logo.png")
    monkeypatch.setattr(cli, "base_folder", lambda: tmp_path)

    code = cli.main(["--size", "", "--effect", "monochrome"])

    printed = capsys.readouterr().out
    assert code == 1
    assert "FAILED  photo.jpg" in printed
    assert "1-bit" in printed
    assert output_files(tmp_path) == ["logo.png"]


def test_the_format_is_printed_before_the_run(tmp_path, monkeypatch, capsys):
    make_input(tmp_path, {"a.png": (8, 8)})
    monkeypatch.setattr(cli, "base_folder", lambda: tmp_path)

    cli.main(["--size", "", "--effect", "none"])
    assert "Format:  same as the input" in capsys.readouterr().out

    cli.main(["--size", "", "--effect", "none", "--format", "png"])
    assert "Format:  png" in capsys.readouterr().out
