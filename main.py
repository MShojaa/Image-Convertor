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

# What the page actually needs. Wide rather than tall, because past 62rem the
# layout puts the controls and the log side by side -- and height is the scarce
# one: a 1080p screen at 125% scaling is only 864 logical pixels tall, where it
# is 1536 wide. Two columns turn the spare width into log height.
WANTED_SIZE = (1220, 860)

# Small enough to still be usable on a laptop, large enough that the layout
# does not collapse into a column of squeezed panels.
MIN_SIZE = (720, 560)

# Left for the taskbar and the window's own titlebar and borders, in the same
# logical pixels as everything else here. webview reports the whole screen, not
# the work area, so a window sized to the full height would have its bottom edge
# behind the taskbar -- and the Convert button is at the bottom.
SCREEN_MARGIN = (64, 96)


def base_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def display_scale() -> float:
    """How many physical pixels Windows draws per logical one.

    1.25 at the 125% display scaling that is the Windows default on a 1080p
    laptop, and the reason this function exists at all.
    """
    try:
        import ctypes

        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        # Not Windows, or too old to ask. 1.0 makes the caller behave exactly
        # as it did before this was here.
        return 1.0


def window_size() -> tuple[int, int]:
    """As big as the page wants, and never bigger than the screen.

    **The two are measured in different units, and that was a real bug.**
    `create_window` takes logical pixels -- the same ones CSS uses -- while
    `webview.screens` reports physical ones. At 125% scaling a 1920x1080 screen
    is 1536x864 logical, so asking for a 940-tall window was asking for 1175
    physical pixels on a screen with 1080. Windows clamped it, the page came up
    shorter than it needed, and it scrolled.

    So the screen is converted into logical pixels before anything is compared,
    and the margin below is in logical pixels too.
    """
    wanted_width, wanted_height = WANTED_SIZE

    try:
        screen = webview.screens[0]
        scale = display_scale()
        available = (
            int(screen.width / scale) - SCREEN_MARGIN[0],
            int(screen.height / scale) - SCREEN_MARGIN[1],
        )
    except Exception:
        # No screen to ask -- take what the page wants and let the window
        # manager sort it out rather than failing to open at all.
        return WANTED_SIZE

    return (
        max(MIN_SIZE[0], min(wanted_width, available[0])),
        max(MIN_SIZE[1], min(wanted_height, available[1])),
    )


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

    width, height = window_size()

    api = Api(base_folder())
    window = webview.create_window(
        WINDOW_TITLE,
        str(index),
        js_api=api,
        width=width,
        height=height,
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
