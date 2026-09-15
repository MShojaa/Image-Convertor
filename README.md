# Image-Convertor

A CLI that converts a folder of images to 1-bit monochrome BMP files.

- Transparent areas become white.
- Resizing only shrinks and always keeps the aspect ratio. A box with a
  different ratio is filled with white around the image rather than stretching
  it: a 20x16 image asked for 10x10 is resized to 10x8 and centred in a 10x10
  white box.
- Press enter at the size question to convert without resizing.
- Resizing never enlarges, so an image already inside the box is centred
  on white at that size and a warning says so -- per image as it happens,
  and again at the end, where a run that shrank nothing at all is called
  out as such.
- Two ways to reach black and white, and the app asks which: **dither**,
  which scatters dots to keep shading and suits photographs, or **hard cut**,
  one threshold with flat areas left flat, which suits line art, icons, logos
  and text.

## Getting started

    scripts\setup.bat            once, creates .venv and installs everything
    scripts\dev.bat              run from source
    scripts\check.bat            run the tests -- all green before a commit
    scripts\build.bat            freeze to dist\Image-Convertor.exe
    scripts\run.bat              run the built exe
    scripts\build-and-run.bat    both

Add `onedir` to `build.bat`/`run.bat`/`build-and-run.bat` for a folder build.

## Using it

The app reads every image in the `input` folder beside it and writes the
results to an `output` folder beside it -- for the exe that is `dist\`, and
running from source that is the project root. If there is no `input` folder it
asks for a path to one. Then it asks for a size, and for how grey should become
black and white.

## Flags

Mostly for scripting; the app asks for what it needs without them.

    --input FOLDER       read from this folder instead of input\
    --size WxH           skip the size question (pass '' for no resizing)
    --mode dither        scattered dots, keeps shading; for photos
    --mode hard-cut      one threshold, flat stays flat; for line art
    --threshold 0-255    where a hard cut splits, default 128 (implies
                         --mode hard-cut)

## Tests

`scripts\check.bat` runs them; it passes its arguments to pytest, so
`scripts\check.bat -k hard_cut` runs a subset and `-x` stops at the first
failure. They cover the rules that are easy to break by accident: transparency
landing on white, the aspect-ratio fit and its centring, shrink-only resizing,
the two black-and-white modes, and what the app asks for and accepts.

## Working on it

`docs/` holds the rest, and `docs/workflow.md` is the one to read first -- it is
the standing rules for how changes get made here: a branch per change, the tests
before a commit, and `scripts\merge.bat` to land one. `docs/graphify.md` is the
knowledge graph the repo builds of itself, and `docs/TODO.md` is what is
specified and not yet written.
