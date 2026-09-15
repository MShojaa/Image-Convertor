# Image-Convertor

A small Windows app that converts, resizes and applies effects to a folder of
images.

- Output is written in the same format as the input by default -- a png in gives
  a png out -- or in one format for everything.
- Transparent areas become white.
- Resizing only shrinks and always keeps the aspect ratio. A box with a
  different ratio is filled with white around the image rather than stretching
  it: a 20x16 image asked for 10x10 is resized to 10x8 and centred in a 10x10
  white box.
- Resizing never enlarges, so an image already inside the box is centred on
  white at that size and a warning says so -- per image as it happens, and again
  at the end, where a run that shrank nothing at all is called out as such.
- Effects are chosen, not compulsory: **blur**, **noise** and **monochrome**.

## Getting started

    scripts\setup.bat            once, creates .venv and installs everything
    scripts\dev.bat              run from source, with devtools on right-click
    scripts\check.bat            run the tests -- all green before a commit
    scripts\build.bat            freeze to dist\Image-Convertor.exe
    scripts\run.bat              run the built exe
    scripts\build-and-run.bat    both

Add `onedir` to `build.bat`/`run.bat`/`build-and-run.bat` for a folder build.

## Using it

The app reads every image in the `input` folder beside it and writes the results
to an `output` folder beside it -- for the exe that is `dist\`, and running from
source that is the project root. If there is no `input` folder it offers the one
you used last time, and Browse picks another.

Then choose a size, a format and any effects, and press Convert. Every file is
reported as it goes, and a file that fails does not stop the batch.

### The effects

They run in this order whichever you pick, because most other orders are wrong
-- monochrome leaves an image with two levels, so anything working on grey has
to come first.

    blur        gaussian blur, default 1 pixel; fractional radii are the
                useful ones on a small image
    noise       uniform noise, default 25 grey levels either way; the seed
                defaults to 0, not the clock, so the same folder converts
                the same way twice
    monochrome  black and white; with a threshold it is a hard cut, without
                one it dithers

**Blur into a hard cut** is the pairing worth knowing about: it is how a
threshold gets a soft edge rather than a jagged one. **Noise into a hard cut**
is a hand-rolled dither, and a coarse one. Blur into a dither mostly cancels
out, because dithering is already scattering dots to fake the grey levels the
blur just made.

### Formats and one bit

`monochrome` makes an image 1-bit, and not every format can hold that. **png,
bmp and tiff** keep it. **gif and webp** store it as grey or as a palette, which
looks identical because there are only two levels in it -- webp is written
lossless in that case so the dots survive. **jpg is refused**: it is lossy, so a
dither comes back with ringing around every dot, and Pillow writes it anyway as
8-bit grey rather than complaining. The app stops instead and says to use png,
bmp or tiff.

Only that pairing is refused. A colour jpg converts to a jpg as you would
expect, and in a mixed folder the one refused file fails on its own while the
rest convert.

## What it remembers

After a run it remembers the folder, the size, the format and the effects, in
`%LOCALAPPDATA%\Image-Convertor\settings.json`, along with the theme. With no
`input\` beside the app it offers the folder you used last time, and only if
that folder is still there and still has images in it.

It is a convenience and it is treated as one -- a settings file that is missing,
unreadable, or hand-edited into nonsense falls back to the defaults rather than
complaining.

## Dark and light

The button in the corner cycles System, Dark, Light. **System is the default**
and follows the OS, including while the window is open; picking Dark or Light
outright sticks until you change it.

## Tests

`scripts\check.bat` runs them; it passes its arguments to pytest, so
`scripts\check.bat -k hard_cut` runs a subset and `-x` stops at the first
failure. They cover the rules that are easy to break by accident: transparency
landing on white, the aspect-ratio fit and its centring, shrink-only resizing,
the effects and the format pairings, what is remembered and every way that file
can be wrong, and what the window is allowed to ask the app to do.

`UI/` itself is not covered -- there is no JavaScript runner in this project.
Everything the page can ask for is tested through `image_convertor/webapi.py`,
and the page is checked by running the app.

## Working on it

`docs/` holds the rest, and `docs/workflow.md` is the one to read first -- it
is the standing rules for how changes get made here: a branch per change, the
tests before a commit, and `scripts\merge.bat` to land one.
`docs/design-system.md` is what the window looks like and why,
`docs/graphify.md` is the knowledge graph the repo builds of itself, and
`docs/TODO.md` is what is specified and not yet written.
