"""What the app remembers, and everything it does when the file is wrong.

The defaults and the round trip are two tests. The rest of this file is the
bad-file cases, because that is where a settings module actually earns its
keep: the file can be hand-edited, half-written by a machine that lost power,
or left by a newer version. None of those may raise, and none of them may lose
more than the key that was bad.
"""

from __future__ import annotations

import json

import pytest

from image_convertor import settings


@pytest.fixture
def stored(isolated_settings):
    """Write raw text into the settings file, whatever it is."""

    def write(text):
        settings.path().parent.mkdir(parents=True, exist_ok=True)
        settings.path().write_text(text, encoding="utf-8")

    return write


# --- where it lives ------------------------------------------------------

def test_it_lives_in_the_user_profile(isolated_settings):
    assert settings.path().parent == isolated_settings / settings.APP_FOLDER
    assert settings.path().name == settings.FILENAME


def test_the_location_is_read_each_time_not_cached():
    """The tests rely on this, and so does a user whose profile moves."""
    assert settings.folder() == settings.folder()


# --- the ordinary path ---------------------------------------------------

def test_no_file_gives_the_defaults():
    assert settings.load() == settings.Settings()


def test_what_is_saved_comes_back():
    saved = settings.Settings(
        input_folder=r"D:\pictures",
        size="128x64",
        output_format="png",
        effects=("blur:2", "monochrome:128"),
        theme="light",
    )

    assert settings.save(saved) is True
    assert settings.load() == saved


def test_remember_changes_one_field_and_leaves_the_rest():
    settings.save(settings.Settings(size="10x10", theme="light"))

    settings.remember(size="20x20")

    after = settings.load()
    assert after.size == "20x20"
    assert after.theme == "light"


def test_the_file_is_readable_json():
    """It is in the user's profile; someone will open it."""
    settings.save(settings.Settings(size="8x8"))

    assert json.loads(settings.path().read_text(encoding="utf-8"))["size"] == "8x8"


# --- when the file is wrong ----------------------------------------------

def test_unparseable_json_falls_back_to_the_defaults(stored):
    stored("{not json at all")

    assert settings.load() == settings.Settings()


def test_a_half_written_file_falls_back_to_the_defaults(stored):
    """What a machine that lost power mid-write leaves behind."""
    stored('{"size": "128x6')

    assert settings.load() == settings.Settings()


def test_an_empty_file_falls_back_to_the_defaults(stored):
    stored("")

    assert settings.load() == settings.Settings()


@pytest.mark.parametrize("text", ["[]", '"a string"', "42", "null"])
def test_json_that_is_not_an_object_falls_back_to_the_defaults(stored, text):
    stored(text)

    assert settings.load() == settings.Settings()


def test_one_bad_key_costs_only_that_key(stored):
    """The point of reading field by field rather than in one go."""
    stored(json.dumps({"size": "64x64", "theme": {"not": "a string"}}))

    loaded = settings.load()
    assert loaded.size == "64x64"
    assert loaded.theme == settings.Settings().theme


def test_effects_of_the_wrong_shape_are_dropped(stored):
    stored(json.dumps({"effects": "blur:2", "size": "8x8"}))

    loaded = settings.load()
    assert loaded.effects == ()
    assert loaded.size == "8x8"


def test_a_list_of_non_strings_is_dropped_whole(stored):
    stored(json.dumps({"effects": ["blur:2", 7]}))

    assert settings.load().effects == ()


def test_keys_from_a_newer_version_are_ignored_not_fatal(stored):
    """An older build must still start against a file it does not understand."""
    stored(json.dumps({"size": "8x8", "watermark": "yes", "quality": 90}))

    assert settings.load().size == "8x8"


def test_a_missing_key_takes_its_default(stored):
    """Which is also how a field added later reads an older file."""
    stored(json.dumps({"size": "8x8"}))

    assert settings.load().theme == settings.Settings().theme


# --- when it cannot be written -------------------------------------------

def test_saving_says_so_rather_than_raising(monkeypatch):
    """A full disk or a profile on a share that went away."""
    def refuse(*args, **kwargs):
        raise OSError("nope")

    monkeypatch.setattr(settings.Path, "write_text", refuse)

    assert settings.save(settings.Settings()) is False


def test_a_file_that_cannot_be_read_gives_the_defaults(monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("nope")

    monkeypatch.setattr(settings.Path, "read_text", refuse)

    assert settings.load() == settings.Settings()


def test_a_file_that_is_not_utf8_gives_the_defaults(isolated_settings):
    settings.path().parent.mkdir(parents=True, exist_ok=True)
    settings.path().write_bytes(b"\xff\xfe\x00\x00 not text")

    assert settings.load() == settings.Settings()
