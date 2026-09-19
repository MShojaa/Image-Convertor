"""What the window is allowed to ask the app to do.

Every method here is reachable from JavaScript through pywebview's `js_api`,
and nothing else is. That is the boundary: `converter.py` and `effects.py` know
nothing about a window, and this file is the only place that knows about both.

Two consequences worth knowing before changing anything here.

**Everything crossing this line is JSON.** Not a `Path`, not a `Size`, not an
`Effect` -- strings, numbers, lists and dicts. A `Path` arrives on the other
side as an empty object, silently, which is the kind of bug that takes an hour.
So every method returns plain data, and every error comes back as
`{"ok": False, "error": "..."}` rather than raising: an exception in a `js_api`
method reaches JavaScript as a rejected promise with pywebview's own message in
it, not the sentence written here.

**The conversion runs on a worker thread.** pywebview's event loop is the GUI
thread, and a batch of two hundred images on it freezes the window for the
length of the batch -- which looks exactly like a crash. `start_conversion`
returns immediately and the work reports back by calling into the page.
"""

from __future__ import annotations

import threading
from pathlib import Path

from . import formats, settings
from .converter import convert_image, find_images, parse_size
from .effects import REGISTRY, describe, order_effects, parse_effect

INPUT_NAME = "input"
OUTPUT_NAME = "output"


def _ok(**data: object) -> dict:
    return {"ok": True, **data}


def _fail(message: str) -> dict:
    return {"ok": False, "error": message}


class Api:
    """The object handed to pywebview as `js_api`.

    One instance per window. It holds the base folder, the window handle once
    there is one, and the flag that a running conversion watches.
    """

    #: Every attribute here is underscored, and that is not a style choice.
    #: pywebview builds the JavaScript proxy by walking `dir()` of this object,
    #: skipping names that start with an underscore and **recursing into every
    #: other non-callable attribute it finds**. A plain `self._window` therefore
    #: points it back at the pywebview Window, into `window.native`, and down
    #: through WinForms until it hits Python's recursion limit -- thousands of
    #: logged errors, on the GUI thread, before the page's first call returns.
    #: The window shows, the page never finishes building, and Windows paints
    #: the title "Image Convertor (Not Responding)".
    #:
    #: So: nothing public on this class except the methods the page may call.
    def __init__(self, base: Path) -> None:
        self._base = base
        self._window = None
        self._cancel = threading.Event()
        self._running = False
        self._choosing = False

    def attach(self, window: object) -> None:
        """Give the Api its window, once create_window has made one.

        A method rather than an attribute the caller sets, so that the name it
        is stored under stays this file's business -- and this file is where
        the reason for that name is written down.
        """
        self._window = window

    # -- what the page needs to draw itself -------------------------------

    def describe_app(self) -> dict:
        """Everything the page needs at startup, in one call.

        One call rather than five: each one is a round trip through the
        bridge, and a window that draws itself in stages is a window with five
        chances to draw itself half way.
        """
        stored = settings.load()
        beside = self._base / INPUT_NAME

        return _ok(
            effects=[
                {
                    "name": name,
                    "order": kind.order,
                    # Each setting says what kind of control it is, so the
                    # page can draw a dropdown or a checkbox rather than a
                    # text box for everything and a user left guessing that
                    # "soft" wants the word "yes".
                    "settings": [
                        {
                            "name": setting.label,
                            "title": setting.shown(),
                            "kind": setting.kind,
                            "options": list(setting.options),
                            "default": _default_for(kind, setting.label),
                        }
                        for setting in _settings_of(kind)
                    ],
                }
                # In the order they run. The page lists them this way because
                # that order is a real thing the user needs to know.
                for name, kind in sorted(REGISTRY.items(), key=lambda p: p[1].order)
            ],
            formats=[
                {"name": fmt.name, "keeps_one_bit": fmt.keeps_one_bit, "note": fmt.note}
                for fmt in formats.REGISTRY.values()
            ],
            input_folder=str(beside) if beside.is_dir() else stored.input_folder,
            has_folder_beside=beside.is_dir(),
            # Unlike the input there is nothing to check: an output folder is
            # somewhere to write, and it is allowed not to exist yet -- the
            # first run that needs it creates it.
            output_folder=stored.output_folder or str(self._base / OUTPUT_NAME),
            default_output_folder=str(self._base / OUTPUT_NAME),
            settings={
                "size": stored.size,
                "output_format": stored.output_format,
                "effects": _still_valid(stored.effects),
                "theme": stored.theme,
            },
        )

    def choose_folder(self, which: str = "input") -> dict:
        """Open the native folder picker. The answer arrives as an event.

        One opener for both fields; `which` comes back on the event so the
        page knows which box to fill in.

        **It must not open the dialog here**, and this is the one thing in this
        file that is not a matter of taste. A `js_api` method runs while the
        page is awaiting its result, and `create_file_dialog` puts its work on
        the GUI thread and waits -- so opening it from inside a `js_api` call
        is two waits pointing at each other. The window locks up, no dialog
        ever appears, and Windows paints it as Not Responding. There is no
        error and nothing to see in a log.

        So the dialog goes on a thread of its own, this returns immediately,
        and the result comes back through `_emit` like everything else the app
        does in the background. The page listens for `folder_chosen`.
        """
        if self._window is None:
            return _fail("No window yet.")

        if self._choosing:
            # The dialog is modal but the page is not: a second click while
            # the first is open would open a second one behind it.
            return _fail("A folder dialog is already open.")

        if which not in ("input", "output"):
            return _fail(f"Unknown folder: {which}")

        self._choosing = True
        threading.Thread(target=self._choose_folder, args=(which,), daemon=True).start()
        return _ok(opening=True)

    def _choose_folder(self, which: str) -> None:
        """The dialog, on its own thread, reporting back when it closes."""
        import webview

        try:
            chosen = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception as error:
            self._emit("folder_chosen", dict(_fail(str(error)), which=which))
            return
        finally:
            self._choosing = False

        if not chosen:
            # Cancelled, which is not a failure -- the page leaves the folder
            # it already had rather than clearing it.
            self._emit("folder_chosen", dict(_ok(folder=None), which=which))
            return

        if which == "output":
            # Nothing to count or to check: it is somewhere to write.
            self._emit(
                "folder_chosen", dict(_ok(folder=str(chosen[0])), which="output")
            )
            return

        self._emit("folder_chosen", dict(self.inspect_folder(chosen[0]), which="input"))

    def inspect_folder(self, folder: str) -> dict:
        """What is in a folder, for the page to show before anything runs."""
        path = Path(folder).expanduser()
        if not path.is_dir():
            return _fail(f"Not a folder: {path}")

        images = find_images(path)
        return _ok(
            folder=str(path),
            count=len(images),
            names=[image.name for image in images[:200]],
        )

    def check_size(self, text: str) -> dict:
        """Validate a size box as it is typed, so the error is not a surprise."""
        try:
            box = parse_size(text)
        except ValueError as error:
            return _fail(str(error))
        return _ok(size=str(box) if box else "")

    _THEMES = ("system", "dark", "light")

    def save_theme(self, theme: str) -> dict:
        """The one setting the page writes on its own, as soon as it changes.

        "system" is a stored choice like the other two, not the absence of one:
        the page resolves it against the OS every time it is applied, so a
        window left open follows the OS changing under it.
        """
        if theme not in self._THEMES:
            return _fail(f"Unknown theme: {theme}")
        settings.remember(theme=theme)
        return _ok(theme=theme)

    # -- doing the work ---------------------------------------------------

    def start_conversion(
        self,
        folder: str,
        size: str,
        output_format: str,
        effects: list[str],
        remember: bool = True,
        output_folder: str = "",
    ) -> dict:
        """Check everything, then start the batch on a worker thread.

        Everything that can be wrong about the request is found here, on the
        GUI thread, before the worker starts -- so a typo comes back as a
        message beside the control that caused it rather than as a failed run.
        """
        if self._running:
            return _fail("A conversion is already running.")

        source = Path(folder).expanduser() if folder else self._base / INPUT_NAME
        if not source.is_dir():
            return _fail(f"Not a folder: {source}")

        images = find_images(source)
        if not images:
            return _fail(f"No images to convert in: {source}")

        destination = (
            Path(output_folder).expanduser()
            if output_folder
            else self._base / OUTPUT_NAME
        )

        # Writing the results into the folder being read is the one arrangement
        # that goes wrong on its own: the outputs are images in the input
        # folder, so the next run converts its own output -- and with "same as
        # the input" that run overwrites the originals.
        if _same_folder(destination, source):
            return _fail(
                "The output folder is the input folder. The next run would "
                "convert these results again, and overwrite the originals. "
                "Choose somewhere else."
            )

        refusal = _unwritable(destination)
        if refusal:
            return _fail(refusal)

        try:
            box = parse_size(size)
            chosen = formats.resolve(output_format) if output_format else None
            chosen_effects = tuple(parse_effect(text) for text in effects)
        except ValueError as error:
            return _fail(str(error))

        self._cancel.clear()
        self._running = True

        worker = threading.Thread(
            target=self._convert_all,
            args=(
                source, images, box, chosen, chosen_effects, remember, destination,
            ),
            daemon=True,   # a window closed mid-batch should not hold the app open
        )
        worker.start()

        return _ok(count=len(images), effects=describe(chosen_effects))

    def cancel_conversion(self) -> dict:
        """Ask the running batch to stop after the file it is on."""
        self._cancel.set()
        return _ok()

    def _convert_all(
        self, source, images, box, chosen, effects, remember, output_folder
    ) -> None:
        """The batch, on the worker thread. Reports every file back to the page."""
        converted = failed = 0
        not_shrunk: list[str] = []

        try:
            for index, image_path in enumerate(images, start=1):
                if self._cancel.is_set():
                    self._emit("conversion_cancelled", {"done": index - 1})
                    return

                written_as = chosen or formats.for_source(image_path)
                destination = formats.destination_for(image_path, output_folder, written_as)

                try:
                    result = convert_image(image_path, destination, box, effects, written_as)
                except Exception as error:
                    # One bad file does not stop a batch -- the same rule the
                    # command line had. The page shows it and carries on.
                    failed += 1
                    self._emit("file_failed", {
                        "index": index, "total": len(images),
                        "name": image_path.name, "error": str(error),
                    })
                    continue

                converted += 1
                payload = {
                    "index": index, "total": len(images),
                    "name": image_path.name, "written": destination.name,
                    "size": str(result.size),
                }
                if result.too_small_to_shrink:
                    not_shrunk.append(image_path.name)
                    payload["warning"] = (
                        f"already {result.original}, smaller than {result.size}"
                        " -- centred on white, not shrunk"
                    )
                self._emit("file_converted", payload)

            if remember and converted:
                beside = self._base / INPUT_NAME
                default_output = self._base / OUTPUT_NAME
                settings.remember(
                    input_folder="" if source == beside else str(source),
                    output_folder=(
                        "" if output_folder == default_output else str(output_folder)
                    ),
                    size=str(box) if box else "",
                    output_format=chosen.name if chosen else "",
                    effects=tuple(e.described() for e in order_effects(effects)),
                )

            self._emit("conversion_finished", {
                "converted": converted,
                "failed": failed,
                "not_shrunk": not_shrunk,
                "all_too_small": bool(not_shrunk) and len(not_shrunk) == converted,
                "box": str(box) if box else "",
                "output_folder": str(output_folder),
            })
        finally:
            self._running = False

    def _emit(self, event: str, payload: dict) -> None:
        """Call a function on the page, from the worker thread.

        Wrapped because there may be no window at all -- which is how the
        tests drive this class -- and because a page that has navigated or
        closed under us is not a reason to lose the rest of the batch.
        """
        if self._window is None:
            return
        try:
            self._window.evaluate_js(f"window.onAppEvent({event!r}, {_json(payload)})")
        except Exception:
            pass


def _still_valid(remembered: tuple[str, ...]) -> list[str]:
    """The remembered effects that this version can still read.

    A settings file is written by whichever version ran last, and an effect's
    settings can change between them -- `monochrome:128:no` meant something in
    4.3 and means nothing now. Handing one of those to the page would tick the
    box, and then every run would fail on it until the user worked out which
    row to untick.

    So an effect that no longer parses is dropped, quietly, the same way
    `settings.load` drops a key it cannot read. The alternative is an app that
    will not convert anything because of a file it wrote itself.
    """
    kept = []
    for text in remembered:
        try:
            parse_effect(text)
        except ValueError:
            continue
        kept.append(text)
    return kept


def _same_folder(one: Path, other: Path) -> bool:
    """Whether two paths are the same folder, following links and shorthand.

    Compared resolved rather than as typed: "." and an absolute path and a
    path through a symlink are all the same folder, and the check that uses
    this is there to stop a run that would eat its own input.
    """
    try:
        return one.resolve() == other.resolve()
    except OSError:
        return False


def _unwritable(folder: Path) -> str | None:
    """Why the results cannot be written there, or None if they can.

    Checked before the batch rather than discovered on the first file: a
    folder that cannot be written is the same answer for all two hundred of
    them, and by the time a save fails the conversion has already been done.
    """
    if folder.exists() and not folder.is_dir():
        return f"Not a folder: {folder}"

    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return f"Cannot create {folder}: {error}"

    probe = folder / ".image-convertor-write-test"
    try:
        probe.touch()
        probe.unlink()
    except OSError as error:
        return f"Cannot write to {folder}: {error}"

    return None


def _json(payload: dict) -> str:
    import json

    return json.dumps(payload)


def _settings_of(kind) -> tuple:
    from .effects import SETTINGS

    return SETTINGS.get(kind, ())


def _default_for(kind, label: str) -> object:
    """An effect's default for one setting, read off the class itself.

    Turned into something JSON can carry: a colour is a tuple in Python and
    has to cross as the hex the user would type, and a flag as the word.
    """
    import dataclasses

    for field in dataclasses.fields(kind):
        if field.name != label:
            continue
        value = field.default
        if isinstance(value, tuple):
            return "#{:02x}{:02x}{:02x}".format(*value[:3])
        if isinstance(value, bool):
            return "yes" if value else "no"
        return value
    return None
