"""Opens the window. The whole entry point.

Everything the window can ask for is in `image_convertor/webapi.py`; the
conversion itself is in `image_convertor/converter.py` and knows about neither.

Where "beside the app" is, is decided here and handed to the Api, rather than
worked out again further in. A frozen onefile build unpacks itself into a temp
folder, so the module path is useless there and `sys.executable` is the exe the
user actually double-clicked; from source there is no exe to be beside, and the
working directory is the honest answer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import webview

from image_convertor import __version__
from image_convertor.webapi import Api

WINDOW_TITLE = "Image Convertor"
MIN_SIZE = (720, 620)


def base_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def ui_folder() -> Path:
    """Where index.html is.

    PyInstaller unpacks bundled data under `sys._MEIPASS`; from source the UI
    sits beside this file. build.py is what puts it there, and the two have to
    agree -- a window that opens on a blank page is almost always this.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "UI"
    return Path(__file__).resolve().parent / "UI"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="Image-Convertor",
        description="Convert, resize and apply effects to a folder of images.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Open the webview's devtools on right-click. For working on the UI.",
    )
    args = parser.parse_args(argv)

    index = ui_folder() / "index.html"
    if not index.is_file():
        print(f"The UI is missing: {index}")
        return 1

    api = Api(base_folder())
    window = webview.create_window(
        WINDOW_TITLE,
        str(index),
        js_api=api,
        width=880,
        height=720,
        min_size=MIN_SIZE,
    )
    # The Api needs the window to open a folder dialog and to call into the
    # page, and create_window is the only place it exists. It goes on a private
    # attribute deliberately -- see the note in Api.__init__, which is the
    # difference between a working window and one that says Not Responding.
    api.attach(window)

    webview.start(debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
