"""The command line app: find the images, ask for a size, convert the lot.

Input comes from an "input" folder beside the app, output goes to an "output"
folder beside it. Beside the app means beside the .exe for a frozen build and
the current working directory when running from source -- see base_folder().
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .converter import (
    DEFAULT_THRESHOLD,
    Size,
    convert_image,
    find_images,
    parse_size,
)

INPUT_NAME = "input"
OUTPUT_NAME = "output"


def base_folder() -> Path:
    """Where "beside the app" is.

    PyInstaller unpacks a onefile build into a temp folder, so the module path
    is useless there; sys.executable is the exe the user actually double
    clicked. From source there is no exe to be beside, so the working
    directory is the honest answer -- and it is why scripts\\run.bat runs the
    exe from dist\\ rather than from the project root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def ask(prompt: str) -> str:
    """input(), but a Ctrl-C or a closed stdin quits instead of exploding."""
    try:
        # A leading BOM turns up when input is piped in from PowerShell and
        # would make a perfectly good path look like a missing folder.
        return input(prompt).lstrip("\ufeff")
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(1) from None


def ask_input_folder(default: Path) -> Path:
    """Get a folder holding images, asking until we are given a real one.

    Only reached when there is no input folder beside the app, which is the
    normal state the first time someone runs it.
    """
    print(f"No {INPUT_NAME!r} folder found at: {default}")
    print("Enter the path to a folder of images (or press enter to quit).")

    while True:
        answer = ask("Images folder: ").strip().strip('"')
        if not answer:
            raise SystemExit(0)

        folder = Path(answer).expanduser()
        if not folder.is_dir():
            print(f"  Not a folder: {folder}")
            continue
        if not find_images(folder):
            print(f"  No images in: {folder}")
            continue
        return folder


def ask_size() -> Size | None:
    """Ask for the output box. Enter means leave the images at their size."""
    print()
    print("Resize to (WIDTHxHEIGHT), or press enter to keep the original size.")
    print("Images keep their aspect ratio and are centred on white in the box.")

    while True:
        try:
            return parse_size(ask("Size: "))
        except ValueError as error:
            print(f"  {error}")


def ask_threshold() -> int:
    """Where the hard cut splits. Enter takes the middle."""
    while True:
        answer = ask(f"Cut at grey level 0-255 [{DEFAULT_THRESHOLD}]: ").strip()
        if not answer:
            return DEFAULT_THRESHOLD
        try:
            threshold = int(answer)
        except ValueError:
            print(f"  Expected a whole number, got {answer!r}")
            continue
        if not 0 <= threshold <= 255:
            print("  Must be between 0 and 255.")
            continue
        return threshold


def ask_threshold_mode() -> int | None:
    """Which way to get to black and white. None means dither.

    The two are not better and worse, they suit different pictures, and the
    result is hard to argue with once seen -- so the question is asked rather
    than guessed at, with dithering as the default because a photograph is
    unreadable without it while line art merely looks better without.
    """
    print()
    print("How should grey become black and white?")
    print("  1. Dither      - scattered dots keep shading; best for photos")
    print("  2. Hard cut    - one threshold, flat areas stay flat; best for")
    print("                   line art, icons, logos and text")

    while True:
        answer = ask("Choice [1]: ").strip().lower()
        if answer in ("", "1", "d", "dither"):
            return None
        if answer in ("2", "h", "hard", "hard cut", "hard-cut", "cut"):
            return ask_threshold()
        print(f"  Enter 1 or 2, got {answer!r}")


def run(args: argparse.Namespace) -> int:
    base = base_folder()

    if args.input is not None:
        source_folder = Path(args.input).expanduser()
        if not source_folder.is_dir():
            print(f"Not a folder: {source_folder}")
            return 1
    else:
        source_folder = base / INPUT_NAME
        if not source_folder.is_dir():
            source_folder = ask_input_folder(source_folder)

    images = find_images(source_folder)
    if not images:
        print(f"No images to convert in: {source_folder}")
        return 1

    print(f"Found {len(images)} image(s) in {source_folder}")

    # --size on the command line skips the question, so the app can be driven
    # from a script; otherwise ask, and enter means no resizing.
    box = parse_size(args.size) if args.size is not None else ask_size()
    threshold = resolve_threshold(args)

    output_folder = base / OUTPUT_NAME
    output_folder.mkdir(parents=True, exist_ok=True)

    print()
    print(f"Writing to {output_folder}")
    print()

    failures = 0
    for image_path in images:
        destination = output_folder / (image_path.stem + ".bmp")
        try:
            written = convert_image(image_path, destination, box, threshold)
        except Exception as error:  # a bad file should not stop the batch
            failures += 1
            print(f"  FAILED  {image_path.name}: {error}")
            continue
        print(f"  {image_path.name} -> {destination.name} ({written})")

    print()
    converted = len(images) - failures
    print(f"Done: {converted} converted, {failures} failed.")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="image-convertor",
        description="Convert images to 1-bit monochrome BMP files.",
    )
    parser.add_argument(
        "--input",
        metavar="FOLDER",
        help=f"Read from this folder instead of {INPUT_NAME}\\ beside the app.",
    )
    parser.add_argument(
        "--size",
        metavar="WxH",
        help="Resize box, e.g. 128x64. Omit to be asked; pass '' for no resizing.",
    )
    parser.add_argument(
        "--mode",
        choices=("dither", "hard-cut"),
        help="Skip the mode question. Dither for photos, hard cut for line art.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        metavar="0-255",
        help=(
            f"Where a hard cut splits, default {DEFAULT_THRESHOLD}. "
            "Implies --mode hard-cut."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def resolve_threshold(args: argparse.Namespace) -> int | None:
    """The threshold to convert with, or None to dither.

    Either flag on the command line answers the question, so the app can be
    driven from a script; with neither, ask.
    """
    if args.mode == "dither":
        return None
    if args.mode == "hard-cut":
        return DEFAULT_THRESHOLD if args.threshold is None else args.threshold
    if args.threshold is not None:
        return args.threshold
    return ask_threshold_mode()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.threshold is not None and not 0 <= args.threshold <= 255:
        print("--threshold must be between 0 and 255.")
        return 1

    if args.mode == "dither" and args.threshold is not None:
        print("--threshold is a hard cut setting; it does not go with --mode dither.")
        return 1

    try:
        return run(args)
    except ValueError as error:
        print(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
