"""Freezes the app to dist\\Image-Convertor.exe with PyInstaller.

Every build flag lives here rather than in the .bat files, so a build from a
shell and a build from scripts\\build.bat are the same build. Run with --check
to only run the preflight: it is the same check the build does first, and it
is what setup.bat uses to prove the environment can produce a working exe.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "Image-Convertor"
MINIMUM_PYTHON = (3, 10)


def check() -> bool:
    """Everything that would otherwise produce an exe that dies on launch."""
    ok = True

    if sys.version_info < MINIMUM_PYTHON:
        need = ".".join(str(part) for part in MINIMUM_PYTHON)
        print(f"FAIL  Python {need}+ required, this is {sys.version.split()[0]}")
        ok = False
    else:
        print(f"ok    Python {sys.version.split()[0]}")

    if not (ROOT / ".venv").exists():
        print("warn  No .venv -- run scripts\\setup.bat to get one")

    # The window loads index.html off disk, so a build that did not bundle it
    # opens on a blank page -- which looks like a code fault and is not one.
    if not (ROOT / "UI" / "index.html").is_file():
        print("FAIL  UI\\index.html is missing")
        ok = False
    else:
        print("ok    UI")

    for module, label in (
        ("PIL", "Pillow"),
        ("webview", "pywebview"),
        ("PyInstaller", "PyInstaller"),
    ):
        try:
            __import__(module)
        except ImportError:
            print(f"FAIL  {label} is not installed in {sys.executable}")
            ok = False
        else:
            print(f"ok    {label}")

    return ok


def build(extra: list[str]) -> int:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        # A window, not a console: a GUI app that opens a black box behind
        # itself looks broken, and there is no longer anything to print into it.
        "--windowed",
        "--name",
        NAME,
        # The page and its stylesheet are data, not code -- PyInstaller does
        # not find them by following imports. main.py reads them back out of
        # sys._MEIPASS, and the two have to agree on the folder name.
        "--add-data",
        f"{ROOT / 'UI'}{os.pathsep}UI",
        # Pillow pulls in tkinter through ImageTk; we never use it and it is a
        # few megabytes of DLLs that can fail to freeze cleanly.
        "--exclude-module",
        "tkinter",
        *(extra or ["--onefile"]),
        str(ROOT / "main.py"),
    ]
    print()
    print(" ".join(command))
    print()
    return subprocess.call(command, cwd=ROOT)


def main(argv: list[str]) -> int:
    print("== preflight ====================================")
    if not check():
        print()
        print("Environment cannot build. Run scripts\\setup.bat.")
        return 1

    if "--check" in argv:
        return 0

    code = build([arg for arg in argv if arg != "--check"])
    if code == 0:
        print()
        print(f"Built: {ROOT / 'dist' / (NAME + '.exe')}")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
