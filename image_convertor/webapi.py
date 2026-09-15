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

    def __init__(self, base: Path) -> None:
        self.base = base
        self.window = None
        self._cancel = threading.Event()
        self._running = False

    # -- what the page needs to draw itself -------------------------------

    def describe_app(self) -> dict:
        """Everything the page needs at startup, in one call.

        One call rather than five: each one is a round trip through the
        bridge, and a window that draws itself in stages is a window with five
        chances to draw itself half way.
        """
        stored = settings.load()
        beside = self.base / INPUT_NAME

        return _ok(
            effects=[
                {
                    "name": name,
                    "order": kind.order,
                    "settings": [
                        {"name": label, "default": _default_for(kind, label)}
                        for label, _, _ in _settings_of(kind)
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
            output_folder=str(self.base / OUTPUT_NAME),
            settings={
                "size": stored.size,
                "output_format": stored.output_format,
                "effects": list(stored.effects),
                "theme": stored.theme,
            },
        )

    def choose_folder(self) -> dict:
        """The native folder picker. Returns the folder, or ok with none."""
        if self.window is None:
            return _fail("No window yet.")

        import webview

        chosen = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if not chosen:
            return _ok(folder=None)   # cancelled, which is not a failure
        return self.inspect_folder(chosen[0])

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

    def save_theme(self, theme: str) -> dict:
        """The one setting the page writes on its own, as soon as it changes."""
        if theme not in ("dark", "light"):
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
    ) -> dict:
        """Check everything, then start the batch on a worker thread.

        Everything that can be wrong about the request is found here, on the
        GUI thread, before the worker starts -- so a typo comes back as a
        message beside the control that caused it rather than as a failed run.
        """
        if self._running:
            return _fail("A conversion is already running.")

        source = Path(folder).expanduser() if folder else self.base / INPUT_NAME
        if not source.is_dir():
            return _fail(f"Not a folder: {source}")

        images = find_images(source)
        if not images:
            return _fail(f"No images to convert in: {source}")

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
            args=(source, images, box, chosen, chosen_effects, remember),
            daemon=True,   # a window closed mid-batch should not hold the app open
        )
        worker.start()

        return _ok(count=len(images), effects=describe(chosen_effects))

    def cancel_conversion(self) -> dict:
        """Ask the running batch to stop after the file it is on."""
        self._cancel.set()
        return _ok()

    def _convert_all(self, source, images, box, chosen, effects, remember) -> None:
        """The batch, on the worker thread. Reports every file back to the page."""
        converted = failed = 0
        not_shrunk: list[str] = []
        output_folder = self.base / OUTPUT_NAME

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
                beside = self.base / INPUT_NAME
                settings.remember(
                    input_folder="" if source == beside else str(source),
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
        if self.window is None:
            return
        try:
            self.window.evaluate_js(f"window.onAppEvent({event!r}, {_json(payload)})")
        except Exception:
            pass


def _json(payload: dict) -> str:
    import json

    return json.dumps(payload)


def _settings_of(kind) -> tuple:
    from .effects import SETTINGS

    return SETTINGS.get(kind, ())


def _default_for(kind, label: str) -> object:
    """An effect's default for one setting, read off the class itself."""
    import dataclasses

    for field in dataclasses.fields(kind):
        if field.name == label:
            return field.default
    return None
