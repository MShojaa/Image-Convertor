"""The API the window talks to.

This is where the behaviour that used to be checked through the command line
lives now: which folder is used, what happens to a file that fails, the
"could not shrink" warning, and what is remembered afterwards. The window
itself is not exercised -- there is no JavaScript runner in this project -- so
`UI/app.js` is checked by running the app, and everything it is allowed to ask
for is checked here.

A fake window stands in for pywebview's. It records the events the worker
thread emits instead of evaluating them as JavaScript, which is the only thing
the real one does with them.
"""

from __future__ import annotations

import json
import re

import pytest
from PIL import Image

from image_convertor import settings
from image_convertor.webapi import Api


class FakeWindow:
    """Records what the app would have called on the page."""

    def __init__(self):
        self.events = []
        self.dialog_returns = None

    def evaluate_js(self, script):
        # The real one runs this string. Unpicking it here keeps the tests
        # honest about what actually crosses the bridge: if it is not
        # JSON-serialisable, this raises exactly where the window would have
        # silently done nothing.
        match = re.fullmatch(r"window\.onAppEvent\('(\w+)', (.*)\)", script, re.S)
        assert match, f"not an event call: {script}"
        self.events.append((match.group(1), json.loads(match.group(2))))

    def create_file_dialog(self, *args, **kwargs):
        return self.dialog_returns


@pytest.fixture
def app(tmp_path):
    """An Api rooted at a tmp folder, with a fake window attached."""
    api = Api(tmp_path)
    api.window = FakeWindow()
    return api


@pytest.fixture
def images(tmp_path):
    """An input folder beside the app, with two images of different shapes."""
    folder = tmp_path / "input"
    folder.mkdir()
    Image.new("RGBA", (20, 16), (0, 0, 0, 0)).save(folder / "clear.png")
    Image.new("RGB", (8, 8), (0, 0, 0)).save(folder / "black.png")
    return folder


def run(app, **kwargs):
    """Start a conversion and wait for the worker to finish."""
    request = {"folder": "", "size": "", "output_format": "", "effects": []}
    request.update(kwargs)
    answer = app.start_conversion(**request)
    if answer["ok"]:
        _settle(app)
    return answer


def _settle(app, timeout=10.0):
    import time

    deadline = time.time() + timeout
    while app._running and time.time() < deadline:
        time.sleep(0.01)
    assert not app._running, "the worker thread did not finish"


def events(app, name):
    return [payload for event, payload in app.window.events if event == name]


def outputs(app):
    folder = app.base / "output"
    return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []


# --- what the page is told at startup ------------------------------------

def test_describe_app_lists_the_effects_in_the_order_they_run(app):
    described = app.describe_app()

    assert described["ok"]
    orders = [effect["order"] for effect in described["effects"]]
    assert orders == sorted(orders)
    assert [e["name"] for e in described["effects"]][-1] == "monochrome"


def test_describe_app_gives_each_effect_its_settings_and_defaults(app):
    described = app.describe_app()
    noise = next(e for e in described["effects"] if e["name"] == "noise")

    assert [s["name"] for s in noise["settings"]] == ["amount", "seed"]
    assert noise["settings"][0]["default"] == 25


def test_describe_app_says_which_formats_keep_one_bit(app):
    formats = {f["name"]: f for f in app.describe_app()["formats"]}

    assert formats["png"]["keeps_one_bit"] is True
    assert formats["jpg"]["keeps_one_bit"] is False
    assert formats["jpg"]["note"]


def test_describe_app_is_json_safe(app):
    """Everything crossing the bridge has to survive being serialised."""
    json.dumps(app.describe_app())


def test_the_folder_beside_the_app_is_offered_when_it_exists(app, images):
    described = app.describe_app()

    assert described["has_folder_beside"] is True
    assert described["input_folder"] == str(images)


def test_the_remembered_folder_is_offered_when_there_is_none_beside(app, tmp_path):
    settings.save(settings.Settings(input_folder=r"D:\pictures"))

    described = app.describe_app()

    assert described["has_folder_beside"] is False
    assert described["input_folder"] == r"D:\pictures"


def test_describe_app_returns_the_stored_settings(app):
    settings.save(settings.Settings(size="64x64", effects=("blur:2",), theme="light"))

    described = app.describe_app()

    assert described["settings"]["size"] == "64x64"
    assert described["settings"]["effects"] == ["blur:2"]
    assert described["settings"]["theme"] == "light"


# --- looking at a folder before running ----------------------------------

def test_inspect_folder_counts_the_images(app, images):
    answer = app.inspect_folder(str(images))

    assert answer["ok"]
    assert answer["count"] == 2
    assert answer["names"] == ["black.png", "clear.png"]


def test_inspect_folder_says_so_when_it_is_not_a_folder(app, tmp_path):
    answer = app.inspect_folder(str(tmp_path / "nowhere"))

    assert answer["ok"] is False
    assert "Not a folder" in answer["error"]


def test_inspect_folder_is_happy_with_an_empty_one(app, tmp_path):
    """Empty is a real answer -- the page shows "0 images" rather than an error."""
    empty = tmp_path / "empty"
    empty.mkdir()

    answer = app.inspect_folder(str(empty))

    assert answer["ok"] and answer["count"] == 0


def test_a_cancelled_folder_dialog_is_not_a_failure(app):
    app.window.dialog_returns = None

    answer = app.choose_folder()

    assert answer["ok"] and answer["folder"] is None


def test_choosing_a_folder_returns_what_is_in_it(app, images):
    app.window.dialog_returns = [str(images)]

    answer = app.choose_folder()

    assert answer["ok"] and answer["count"] == 2


# --- checking a size as it is typed --------------------------------------

def test_check_size_accepts_a_box(app):
    assert app.check_size("128x64") == {"ok": True, "size": "128x64"}


def test_check_size_treats_empty_as_no_resizing(app):
    assert app.check_size("") == {"ok": True, "size": ""}


def test_check_size_explains_a_bad_one(app):
    answer = app.check_size("wide")

    assert answer["ok"] is False
    assert "Expected" in answer["error"]


# --- refusing a request before the worker starts -------------------------

def test_a_folder_that_is_not_there_is_refused(app, tmp_path):
    answer = app.start_conversion(str(tmp_path / "nowhere"), "", "", [])

    assert answer["ok"] is False
    assert not app._running


def test_an_empty_folder_is_refused(app, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    answer = app.start_conversion(str(empty), "", "", [])

    assert answer["ok"] is False
    assert "No images" in answer["error"]


def test_a_bad_size_is_refused_with_the_parsers_own_message(app, images):
    answer = app.start_conversion("", "wide", "", [])

    assert answer["ok"] is False
    assert "Expected" in answer["error"]


def test_an_unknown_effect_is_refused_and_names_the_known_ones(app, images):
    answer = app.start_conversion("", "", "", ["sepia"])

    assert answer["ok"] is False
    assert "monochrome" in answer["error"]


def test_an_unknown_format_is_refused(app, images):
    answer = app.start_conversion("", "", "heic", [])

    assert answer["ok"] is False
    assert "heic" in answer["error"]


def test_nothing_is_written_when_the_request_is_refused(app, images):
    app.start_conversion("", "wide", "", [])

    assert outputs(app) == []


# --- converting ----------------------------------------------------------

def test_a_run_converts_the_folder_beside_the_app(app, images):
    answer = run(app)

    assert answer["ok"] and answer["count"] == 2
    assert outputs(app) == ["black.png", "clear.png"]


def test_every_file_is_reported_as_it_goes(app, images):
    run(app)

    reported = events(app, "file_converted")
    assert [r["name"] for r in reported] == ["black.png", "clear.png"]
    assert [r["index"] for r in reported] == [1, 2]
    assert all(r["total"] == 2 for r in reported)


def test_the_run_finishes_with_a_summary(app, images):
    run(app)

    finished = events(app, "conversion_finished")[0]
    assert finished["converted"] == 2
    assert finished["failed"] == 0


def test_the_effects_are_applied(app, images):
    run(app, effects=["monochrome:128"])

    with Image.open(app.base / "output" / "black.png") as result:
        assert result.mode == "1"


def test_the_size_is_applied(app, images):
    run(app, size="10x10")

    with Image.open(app.base / "output" / "clear.png") as result:
        assert result.size == (10, 10)


def test_the_format_is_applied(app, images):
    run(app, output_format="bmp")

    assert outputs(app) == ["black.bmp", "clear.bmp"]


def test_a_file_that_fails_does_not_stop_the_batch(app, images):
    (images / "broken.png").write_bytes(b"not a png")

    run(app)

    assert [f["name"] for f in events(app, "file_failed")] == ["broken.png"]
    assert events(app, "conversion_finished")[0] == {
        **events(app, "conversion_finished")[0],
        "converted": 2,
        "failed": 1,
    }
    assert outputs(app) == ["black.png", "clear.png"]


def test_monochrome_into_jpeg_fails_that_file_and_says_why(app, tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    Image.new("RGB", (8, 8)).save(folder / "photo.jpg")
    Image.new("RGB", (8, 8)).save(folder / "logo.png")

    run(app, effects=["monochrome"])

    failed = events(app, "file_failed")
    assert [f["name"] for f in failed] == ["photo.jpg"]
    assert "1-bit" in failed[0]["error"]
    assert outputs(app) == ["logo.png"]


def test_every_event_is_json_safe(app, images):
    """The FakeWindow parses what it is given, so this is asserted by running."""
    run(app, size="10x10", effects=["blur:1"])

    assert app.window.events


# --- the shrink warning --------------------------------------------------

def test_an_image_already_inside_the_box_is_warned_about(app, images):
    run(app, size="40x40")

    warnings = [e for e in events(app, "file_converted") if "warning" in e]
    assert {w["name"] for w in warnings} == {"black.png", "clear.png"}
    assert "not shrunk" in warnings[0]["warning"]


def test_a_run_that_shrank_nothing_says_so_in_the_summary(app, images):
    run(app, size="40x40")

    finished = events(app, "conversion_finished")[0]
    assert finished["all_too_small"] is True
    assert finished["box"] == "40x40"


def test_a_run_that_shrank_some_names_the_others(app, images):
    run(app, size="10x10")   # 20x16 shrinks, 8x8 does not

    finished = events(app, "conversion_finished")[0]
    assert finished["not_shrunk"] == ["black.png"]
    assert finished["all_too_small"] is False


def test_no_resizing_warns_about_nothing(app, images):
    run(app)

    finished = events(app, "conversion_finished")[0]
    assert finished["not_shrunk"] == []


# --- one at a time, and stopping -----------------------------------------

def test_a_second_conversion_is_refused_while_one_is_running(app, images):
    app._running = True

    answer = app.start_conversion("", "", "", [])

    assert answer["ok"] is False
    assert "already running" in answer["error"]
    app._running = False


def test_cancelling_before_it_starts_stops_it_at_the_first_file(app, images):
    app._cancel.set()
    app._running = True
    app._convert_all(images, sorted(images.iterdir()), None, None, (), False)

    assert events(app, "conversion_cancelled")[0]["done"] == 0
    assert outputs(app) == []


# --- what it remembers ---------------------------------------------------

def test_a_run_remembers_what_it_used(app, images):
    run(app, size="16x16", output_format="png", effects=["blur:2"])

    stored = settings.load()
    assert stored.size == "16x16"
    assert stored.output_format == "png"
    assert stored.effects == ("blur:2",)


def test_the_folder_beside_the_app_is_not_remembered_as_a_path(app, images):
    run(app)

    assert settings.load().input_folder == ""


def test_another_folder_is_remembered(app, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    Image.new("RGB", (4, 4)).save(elsewhere / "one.png")

    run(app, folder=str(elsewhere))

    assert settings.load().input_folder == str(elsewhere)


def test_a_run_can_opt_out_of_remembering(app, images):
    settings.save(settings.Settings(size="99x99"))

    run(app, size="8x8", remember=False)

    assert settings.load().size == "99x99"


@pytest.mark.parametrize("theme", ["dark", "light", "system"])
def test_the_theme_is_saved_on_its_own(app, theme):
    assert app.save_theme(theme) == {"ok": True, "theme": theme}
    assert settings.load().theme == theme


def test_following_the_os_is_the_default(app):
    """An app that ignores the OS setting is the odd one out."""
    assert settings.Settings().theme == "system"
    assert app.describe_app()["settings"]["theme"] == "system"


def test_an_unknown_theme_is_refused(app):
    answer = app.save_theme("neon")

    assert answer["ok"] is False
    assert settings.load().theme == settings.Settings().theme
