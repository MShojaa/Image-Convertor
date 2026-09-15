# Image-Convertor

A CLI that converts, resizes and applies effects to a folder of images.

- Output is written in the same format as the input by default -- a png in
  gives a png out -- or in one format for everything with `--format`.
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
- Effects are chosen, not compulsory: **blur**, **noise** and **monochrome**.
  Monochrome is the 1-bit one, and it has two ways to get there -- **dither**,
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

    --input FOLDER       read from this folder instead of input    --format NAME        png, jpg, bmp, gif, tiff or webp; default is the
                         same format as each input file
    --size WxH           skip the size question (pass '' for no resizing)
    --effect NAME[:V]    an effect to apply, repeatable; --effect none
                         converts with no effects at all
    --mode dither        scattered dots, keeps shading; for photos
    --mode hard-cut      one threshold, flat stays flat; for line art
    --threshold 0-255    where a hard cut splits, default 128 (implies
                         --mode hard-cut)

`--mode` and `--threshold` are the monochrome effect said the short way, and
they still work. `--effect monochrome` and `--effect monochrome:128` are the
same two things.

Effects run in a fixed order whatever order you name them in, and one of each
is applied -- naming the same effect twice keeps the last one. The order is
fixed because most orderings are wrong: monochrome leaves an image with two
levels, so anything working on grey has to come first.

### The effects

    blur[:RADIUS]            gaussian blur, default 1 pixel; fractional
                             radii are the useful ones on a small image
    noise[:AMOUNT[:SEED]]    uniform noise, default 25 grey levels either
                             way; the seed defaults to 0, not the clock
    monochrome[:0-255]       black and white; with a threshold it is a hard
                             cut, without one it dithers

A setting can be left out to take its default, so `--effect noise::7` is the
default amount with seed 7.

The noise **seed is fixed, not the clock**, so converting the same folder twice
gives the same files. Pass a different seed when you want different noise --
that is what the number is for.

### Formats and one bit

`monochrome` makes an image 1-bit, and not every format can hold that.
**png, bmp and tiff** keep it. **gif and webp** store it as grey or as a
palette, which looks identical because there are only two levels in it --
webp is written lossless in that case so the dots survive. **jpg is
refused**: it is lossy, so a dither comes back with ringing around every
dot, and Pillow writes it anyway as 8-bit grey rather than complaining. The
app stops instead, and says to use png, bmp or tiff.

Only that pairing is refused. A colour jpg converts to a jpg as you would
expect.

**Blur into a hard cut** is the pairing worth knowing about: it is how a
threshold gets a soft edge rather than a jagged one. **Noise into a hard
cut** is a hand-rolled dither, and a coarse one -- reach for it when you
want the coarseness, not as a better `monochrome`.

Blur into a dither mostly cancels out, because dithering is already
scattering dots to fake the grey levels the blur just made.

## Tests

`scripts\check.bat` runs them; it passes its arguments to pytest, so
`scripts\check.bat -k hard_cut` runs a subset and `-x` stops at the first
failure. They cover the rules that are easy to break by accident: transparency
landing on white, the aspect-ratio fit and its centring, shrink-only resizing,
the two black-and-white modes, and what the app asks for and accepts.

## What it remembers

After a run it remembers the folder, the size, the format and the effects, in
`%LOCALAPPDATA%\Image-Convertor\settings.json`. The one that does anything
today is the folder: with no `input\` beside the app it offers the folder you
used last time instead of asking again, and only if that folder is still there
and still has images in it.

It is a convenience and it is treated as one -- a settings file that is
missing, unreadable, or hand-edited into nonsense falls back to the defaults
rather than complaining. `--no-remember` turns the whole thing off for a run,
which is what a scripted run wants so it does not change what the next
interactive one does.

## Working on it

`docs/` holds the rest, and `docs/workflow.md` is the one to read first -- it is
the standing rules for how changes get made here: a branch per change, the tests
before a commit, and `scripts\merge.bat` to land one. `docs/graphify.md` is the
knowledge graph the repo builds of itself, and `docs/TODO.md` is what is
specified and not yet written.
