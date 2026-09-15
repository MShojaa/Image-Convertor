"""Entry point, for running from source and for PyInstaller to freeze."""

import sys

from image_convertor.cli import main

if __name__ == "__main__":
    code = main()

    # A double-clicked exe owns its console window and takes it down with it,
    # so the summary would flash past. From source the shell stays around and
    # this would just be in the way.
    if getattr(sys, "frozen", False) and sys.stdin is not None and sys.stdin.isatty():
        try:
            input("\nPress enter to close...")
        except (EOFError, KeyboardInterrupt):
            pass

    raise SystemExit(code)
