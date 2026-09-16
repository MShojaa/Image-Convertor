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
import threading
import time

import pytest
from PIL import Image

from pathlib import Path

from image_convertor import settings
from image_convertor.webapi import Api


class FakeWindow:
    """Records what the app would have called on the page."""

    def __init__(self):
        self.events = []
        self.dialog_returns = None
        self.dialog_error = None
        self.dialog_delay = 0.0
        self.dialog_thread = None   # which thread opened it -- see the tests

    def evaluate_js(self, script):
        # The real one runs this string. Unpicking it here keeps the tests
        # honest about what actually crosses the bridge: if it is not
        # JSON-serialisable, this raises exactly where the window would have
        # silently done nothing.
        match = re.fullmatch(r"window\.onAppEvent\('(\w+)', (.*)\)", script, re.S)
        assert match, f"not an event call: {script}"
        self.events.append((match.group(1), json.loads(match.group(2))))

    def create_file_dialog(self, *args, **kwargs):
        # The real one hands its work to the GUI thread and waits. Recording
        # the caller is how the test below can tell that this was not called
        # from the js_api thread, which is the whole bug.
        self.dialog_thread = threading.current_thread()
        time.sleep(self.dialog_delay)
        if self.dialog_error:
            raise self.dialog_error
        return self.dialog_returns


@pytest.fixture
def app(tmp_path):
    """An Api rooted at a tmp folder, with a fake window attached."""
    api = Api(tmp_path)
    api.attach(FakeWindow())
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
    return [payload for event, payload in app._window.events if event == name]


def outputs(app):
    folder = app._base / "output"
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

    assert [s["name"] for s in noise["settings"]] == ["amount", "seed", "keep_clear"]
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


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def folder_events(app):
    return [payload for event, payload in app._window.events if event == "folder_chosen"]


def test_the_folder_dialog_does_not_open_on_the_calling_thread(app, images):
    """The bug this guards against locked the window with no error at all.

    A js_api method runs while the page awaits its result, and
    create_file_dialog puts its work on the GUI thread and waits. Opening the
    dialog from inside the js_api call is therefore two waits pointing at each
    other: the window freezes, no dialog appears, and Windows paints it Not
    Responding. Nothing is logged, because nothing failed.
    """
    app._window.dialog_returns = [str(images)]
    caller = threading.current_thread()

    app.choose_folder()
    assert wait_for(lambda: app._window.dialog_thread is not None)

    assert app._window.dialog_thread is not caller


def test_choosing_a_folder_returns_immediately(app, images):
    """It cannot wait for the dialog -- that is what deadlocked."""
    app._window.dialog_returns = [str(images)]
    app._window.dialog_delay = 0.5

    started = time.time()
    answer = app.choose_folder()
    elapsed = time.time() - started

    assert answer["ok"] and answer["opening"] is True
    assert elapsed < 0.4, "choose_folder waited for the dialog"
    assert wait_for(lambda: folder_events(app))


def test_the_chosen_folder_arrives_as_an_event(app, images):
    app._window.dialog_returns = [str(images)]

    app.choose_folder()

    assert wait_for(lambda: folder_events(app))
    chosen = folder_events(app)[0]
    assert chosen["ok"] and chosen["folder"] == str(images)
    assert chosen["count"] == 2


def test_a_cancelled_folder_dialog_is_not_a_failure(app):
    app._window.dialog_returns = None

    app.choose_folder()

    assert wait_for(lambda: folder_events(app))
    chosen = folder_events(app)[0]
    assert chosen["ok"] and chosen["folder"] is None


def test_a_dialog_that_raises_is_reported_rather_than_lost(app):
    app._window.dialog_error = RuntimeError("no shell available")

    app.choose_folder()

    assert wait_for(lambda: folder_events(app))
    assert folder_events(app)[0]["ok"] is False


def test_a_second_dialog_is_refused_while_one_is_open(app, images):
    """The dialog is modal but the page is not; a second click would open a
    second dialog behind the first."""
    app._window.dialog_returns = [str(images)]
    app._window.dialog_delay = 0.4

    first = app.choose_folder()
    second = app.choose_folder()

    assert first["ok"] is True
    assert second["ok"] is False
    assert "already open" in second["error"]
    assert wait_for(lambda: folder_events(app))


def test_the_dialog_can_be_opened_again_after_it_closes(app, images):
    app._window.dialog_returns = [str(images)]

    app.choose_folder()
    assert wait_for(lambda: folder_events(app))

    assert app.choose_folder()["ok"] is True


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

    with Image.open(app._base / "output" / "black.png") as result:
        assert result.mode == "1"


def test_the_size_is_applied(app, images):
    run(app, size="10x10")

    with Image.open(app._base / "output" / "clear.png") as result:
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
    # A gradient, so the dither has both black and white in it; a flat square
    # dithers to one level and there is nothing for jpg to ruin.
    gradient = Image.new("L", (32, 8))
    for x in range(32):
        for y in range(8):
            gradient.putpixel((x, y), x * 8)
    gradient.convert("RGB").save(folder / "photo.jpg")
    Image.new("RGB", (8, 8)).save(folder / "logo.png")

    run(app, effects=["monochrome"])

    failed = events(app, "file_failed")
    assert [f["name"] for f in failed] == ["photo.jpg"]
    assert "two-level" in failed[0]["error"]
    assert outputs(app) == ["logo.png"]


def test_every_event_is_json_safe(app, images):
    """The FakeWindow parses what it is given, so this is asserted by running."""
    run(app, size="10x10", effects=["blur:1"])

    assert app._window.events


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
    app._convert_all(
        images, sorted(images.iterdir()), None, None, (), False, app._base / "output"
    )

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


# --- what pywebview sees when it builds the JavaScript proxy --------------

def test_pywebview_can_enumerate_the_api_without_recursing(app, images):
    """The bug that shipped: the window opened and never finished loading.

    pywebview builds its JS proxy by walking dir() of this object, skipping
    underscored names and recursing into every other non-callable attribute.
    A public `self.window` sends it into the pywebview Window, through
    `window.native`, and down WinForms until Python's recursion limit -- and
    it does that on the GUI thread, before the page's first call returns. The
    window paints, the page stays half-built, and the titlebar says Not
    Responding.

    This runs the real traversal, so it fails the way the app failed.
    """
    from webview.util import inspect as _inspect  # noqa: F401  (import check)
    import webview.util as util

    functions = {}
    getter = util.__dict__.get("get_functions")
    if getter is None:
        # get_functions is nested inside another function in some versions;
        # reimplement its rule rather than skip the check.
        functions = _walk_like_pywebview(app)
    else:  # pragma: no cover - depends on the pywebview version
        functions = getter(app)

    assert set(functions) >= {
        "describe_app", "choose_folder", "inspect_folder",
        "check_size", "save_theme", "start_conversion", "cancel_conversion",
    }


def _walk_like_pywebview(obj, base_name="", functions=None, depth=0):
    """pywebview's traversal rule, as webview/util.py implements it.

    Deliberately not depth-limited: a limit here would hide exactly the
    runaway this test exists to catch. It recurses until Python stops it,
    which against the old code it did.
    """
    import inspect

    if functions is None:
        functions = {}

    for name in dir(obj):
        if name.startswith("_"):
            continue
        attr = getattr(obj, name)
        full = f"{base_name}.{name}" if base_name else name

        if inspect.ismethod(attr) or inspect.isfunction(attr):
            functions[full] = True
        elif inspect.isclass(attr) or (
            isinstance(attr, object) and not callable(attr) and hasattr(attr, "__module__")
        ):
            _walk_like_pywebview(attr, full, functions, depth + 1)

    return functions


def test_nothing_public_on_the_api_is_anything_but_a_method(app, images):
    """The rule that keeps the traversal above finite, stated directly."""
    import inspect

    for name in dir(app):
        if name.startswith("_"):
            continue
        attribute = getattr(app, name)
        assert inspect.ismethod(attribute), f"{name} is public and not a method"


def test_the_window_is_not_reachable_from_a_public_attribute(app):
    """The specific cycle that caused it: Api -> Window -> native -> forever."""
    app.attach(FakeWindow())

    reachable = [name for name in dir(app) if not name.startswith("_")]

    assert "window" not in reachable
    assert "base" not in reachable


# --- choosing where the results go ---------------------------------------

def test_the_default_output_folder_is_beside_the_app(app, images):
    described = app.describe_app()

    assert described["output_folder"] == str(app._base / "output")
    assert described["default_output_folder"] == str(app._base / "output")


def test_a_remembered_output_folder_is_offered(app, images, tmp_path):
    elsewhere = str(tmp_path / "results")
    settings.save(settings.Settings(output_folder=elsewhere))

    described = app.describe_app()

    assert described["output_folder"] == elsewhere
    assert described["default_output_folder"] == str(app._base / "output")


def test_the_results_go_where_they_are_asked_to(app, images, tmp_path):
    elsewhere = tmp_path / "results"

    run(app, output_folder=str(elsewhere))

    assert sorted(p.name for p in elsewhere.iterdir()) == ["black.png", "clear.png"]
    assert not (app._base / "output").exists()


def test_an_output_folder_that_does_not_exist_yet_is_created(app, images, tmp_path):
    """It is somewhere to write, not somewhere to read -- it need not be there."""
    deep = tmp_path / "a" / "b" / "c"

    run(app, output_folder=str(deep))

    assert deep.is_dir()
    assert list(deep.iterdir())


def test_writing_into_the_input_folder_is_refused(app, images):
    """The one arrangement that destroys work on its own.

    The results are images in the input folder, so the next run converts its
    own output -- and with "same as the input" that run overwrites the
    originals.
    """
    answer = app.start_conversion(str(images), "", "", [], True, str(images))

    assert answer["ok"] is False
    assert "input folder" in answer["error"]


def test_the_same_folder_spelled_differently_is_still_refused(app, images):
    """Resolved, not compared as typed -- "." and a long path are one folder."""
    answer = app.start_conversion(
        str(images), "", "", [], True, str(images / ".." / images.name)
    )

    assert answer["ok"] is False


def test_a_file_where_the_output_folder_should_be_is_refused(app, images, tmp_path):
    blocker = tmp_path / "results"
    blocker.write_text("not a folder", encoding="utf-8")

    answer = app.start_conversion("", "", "", [], True, str(blocker))

    assert answer["ok"] is False
    assert "Not a folder" in answer["error"]


def test_an_unwritable_output_folder_is_refused_before_the_batch(app, images, monkeypatch, tmp_path):
    """Found up front: it is the same answer for all two hundred files, and by
    the time a save fails the conversion has already been done."""
    def refuse(self, *args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(Path, "touch", refuse)

    answer = app.start_conversion("", "", "", [], True, str(tmp_path / "results"))

    assert answer["ok"] is False
    assert "Cannot write" in answer["error"]


def test_the_output_folder_is_remembered_when_it_is_not_the_default(app, images, tmp_path):
    elsewhere = tmp_path / "results"

    run(app, output_folder=str(elsewhere))

    assert settings.load().output_folder == str(elsewhere)


def test_the_default_output_folder_is_not_remembered_as_a_path(app, images):
    """It is wherever the app is, so today's path would be wrong tomorrow."""
    run(app)

    assert settings.load().output_folder == ""


def test_the_finished_event_names_the_folder_written_to(app, images, tmp_path):
    elsewhere = tmp_path / "results"

    run(app, output_folder=str(elsewhere))

    assert events(app, "conversion_finished")[0]["output_folder"] == str(elsewhere)


# --- one dialog, two fields ----------------------------------------------

def test_the_dialog_says_which_field_it_was_opened_for(app, images, tmp_path):
    app._window.dialog_returns = [str(tmp_path)]

    app.choose_folder("output")

    assert wait_for(lambda: folder_events(app))
    assert folder_events(app)[0]["which"] == "output"


def test_choosing_an_output_folder_does_not_count_images_in_it(app, tmp_path):
    """It is somewhere to write; what is already there is not interesting."""
    app._window.dialog_returns = [str(tmp_path)]

    app.choose_folder("output")

    assert wait_for(lambda: folder_events(app))
    chosen = folder_events(app)[0]
    assert chosen["ok"] and "count" not in chosen


def test_choosing_an_input_folder_still_counts_them(app, images):
    app._window.dialog_returns = [str(images)]

    app.choose_folder("input")

    assert wait_for(lambda: folder_events(app))
    assert folder_events(app)[0]["count"] == 2


def test_an_unknown_field_is_refused(app):
    answer = app.choose_folder("sideways")

    assert answer["ok"] is False
    assert app._choosing is False


def test_a_cancelled_dialog_still_says_which_field(app):
    app._window.dialog_returns = None

    app.choose_folder("output")

    assert wait_for(lambda: folder_events(app))
    assert folder_events(app)[0]["which"] == "output"


# --- what the page is told about each setting ----------------------------

def settings_of(app, effect_name):
    described = app.describe_app()
    effect = next(e for e in described["effects"] if e["name"] == effect_name)
    return {setting["name"]: setting for setting in effect["settings"]}


def test_each_setting_says_what_kind_of_control_it_is(app):
    """So the page can draw a dropdown or a checkbox rather than a text box
    for everything and a user left guessing that "soft" wants the word "yes"."""
    settings = settings_of(app, "transparent")

    assert settings["colour"]["kind"] == "colour"
    assert settings["match"]["kind"] == "choice"
    assert settings["tolerance"]["kind"] == "number"
    assert settings["soft"]["kind"] == "flag"


def test_a_choice_setting_carries_its_options(app):
    assert settings_of(app, "transparent")["match"]["options"] == ["tolerance", "exact"]


def test_a_setting_that_is_not_a_choice_carries_none(app):
    assert settings_of(app, "blur")["radius"]["options"] == []


def test_a_colour_default_crosses_as_the_hex_a_user_would_type(app):
    """It is a tuple in Python, and a tuple is not something the page can put
    in a text box."""
    assert settings_of(app, "transparent")["colour"]["default"] == "#ffffff"
    assert settings_of(app, "grayscale")["tint"]["default"] == "#808080"


def test_a_flag_default_crosses_as_the_word(app):
    assert settings_of(app, "transparent")["soft"]["default"] == "no"


def test_the_transparent_effect_is_offered_first(app):
    """It runs first, and the list is in the order things run."""
    described = app.describe_app()

    assert described["effects"][0]["name"] == "transparent"


def test_a_conversion_can_key_a_colour_out(app, tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    image = Image.new("RGB", (8, 4), (255, 255, 255))
    for x in range(4, 8):
        for y in range(4):
            image.putpixel((x, y), (200, 30, 30))
    image.save(folder / "logo.png")

    run(app, effects=["transparent"])

    with Image.open(app._base / "output" / "logo.png") as result:
        assert result.mode == "RGBA"
        assert result.getchannel("A").getpixel((0, 0)) == 0
        assert result.getchannel("A").getpixel((7, 0)) == 255
