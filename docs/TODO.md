# TODO

Things specified and not yet built, with what finishing each one involves. Not a
wish list -- everything here is a decision already taken that is waiting on
being written.

Nothing below is started. The order is roughly the order to do them in: 1-4 are
independent of each other, 7 changes the shape of 1 and 2 so it wants doing
before there are many effects to retrofit, and 5-6 are the largest piece and
depend on none of it.

The vocabulary shifts here. Today's conversion is one fixed pipeline --
flatten, fit, threshold -- and `--mode dither|hard-cut` chooses the last step.
Items 1, 2 and 7 turn that into a list of **effects** the user picks and orders,
and item 3 stops assuming the output is a monochrome BMP. Both are worth doing
deliberately rather than bolting a flag on each time.

---

## 1. A blur effect

Gaussian blur, as one of the conversion types.

- **Where it goes.** `converter.py`, beside `to_monochrome()`. Pillow already
  has it: `ImageFilter.GaussianBlur(radius)` -- no new dependency.
- **Where in the pipeline.** After the fit, before the black-and-white step.
  Blurring first and shrinking second throws away most of the blur; blurring a
  1-bit image is meaningless because there is nothing between black and white
  left to smear.
- **What to ask.** A radius, in pixels. It needs a default (1.0 is the usual
  starting point) and it is a float, not an int -- radii below 1 are the useful
  ones on small images.
- **Watch for.** Blur plus hard cut is the combination that does something
  visually interesting -- it is how you get a soft-edged threshold rather than a
  jagged one. Blur plus dither mostly cancels out. Worth a line in the README
  saying so, since a user will otherwise try the pairing that does nothing.

## 2. A noise effect

Add noise, as one of the conversion types.

- **Kind.** Decide and write it down: uniform, or Gaussian. Uniform is simpler
  to reason about and easier to expose (one amount, 0-255). Gaussian looks more
  like film grain. Start with uniform unless there is a reason not to.
- **Amount.** One number, the maximum deviation per pixel. It applies to the
  greyscale image, not per channel, since the next step is greyscale anyway.
- **Where in the pipeline.** After the fit, and after blur if both are on --
  noise then blur is just a softer noise, which is not what either flag says it
  does.
- **Determinism.** This is the one that matters for the tests. Noise with no
  seed makes a test that can only assert "something changed". Take a `--seed`,
  default to a fixed value rather than to the clock, and the output is
  reproducible -- which is also what a user converting the same folder twice
  expects.
- **Watch for.** Noise before a hard cut is a hand-rolled dither, and a coarse
  one. Say that in the README next to the blur note.

## 3. An output format

Choose the image format written, rather than always writing a 1-bit BMP.

- **Default: the same as the input.** A `.png` in gives a `.png` out. That is
  the stated default and it is a change in behaviour -- today everything comes
  out `.bmp` -- so it wants a line in the README and, by the rules in
  `workflow.md`, is arguably a **major** bump: a script that globs `output\*.bmp`
  stops finding anything. Raise that at merge time rather than inferring minor
  from the `feat/` prefix.
- **The formats.** `png`, `jpg`, `bmp` (8-bit or 24-bit), and `monochrome
  bitmap` -- today's 1-bit BMP -- at least. The last one is not a format so much
  as a format plus a mode, which is the thing to get right in the design: **the
  output format and the colour depth are two separate questions** that today's
  code answers with one answer.
- **The awkward pairs.** JPEG cannot hold a 1-bit image, and cannot hold
  transparency; `mode "1"` saved as JPEG raises rather than silently converting.
  Every format/depth pair needs to be either supported or refused with a
  sentence saying why -- refusing is fine, failing at `image.save()` with a
  Pillow traceback is not.
- **Where it goes.** `convert_image()` decides the extension today by string
  concatenation in `cli.py` (`image_path.stem + ".bmp"`). That moves into the
  converter with the format.
- **Ask it, like the others.** Same shape as the size and mode questions: a
  prompt with a default, and a `--format` flag that skips it.

## 4. An option for the input folder

Choose where images are read from, without editing anything.

- **Default: `input\` beside the executable**, which is what happens today.
  `--input FOLDER` already exists as a flag and `base_folder()` already resolves
  "beside the executable" correctly for both the frozen exe and a source run --
  so this item is not about the mechanism, it is about **remembering the
  answer**.
- **What is actually missing.** A user who keeps their images somewhere else
  retypes the path every run. The options, in increasing order of work: ask for
  it interactively when `input\` exists too (today the question only appears when
  it does not); remember the last answer in a small config file beside the
  executable; or both.
- **Decide the config question first.** A config file is the first piece of
  persistent state this app would have, and the GUI in item 5 will want one too
  (window size, theme, last folder). Worth designing once, for both, rather than
  writing a one-line JSON dump here and a different one there. Where it lives
  matters for the frozen build: beside the exe, not in the unpack folder.

## 5. A GUI, with pywebview

A window over the same converter, with a `docs/design-system.md` to go with it.

- **`docs/design-system.md` comes first**, not after. It is the palette, the
  type scale, the spacing metrics and the component rules, written down before
  anything is styled, because a stylesheet written first becomes the spec by
  accident and then nobody can change a colour without checking six places.
  **Dark theme first** -- item 6 is the light one.
- **The boundary is the point.** `image_convertor/converter.py` knows nothing
  about the CLI today and must learn nothing about the GUI either. The window
  talks to a small API object; that object calls the same `convert_image()` the
  CLI calls. If the GUI needs a change in `converter.py` that the CLI would not
  want, that is the signal the boundary is being crossed in the wrong place.
- **What the window needs that the CLI does not.** Progress over a folder that
  may hold hundreds of images; a preview of one conversion before running the
  batch; and somewhere to show the "could not shrink" warnings, which in the CLI
  are just lines that scroll past.
- **Threading.** pywebview's event loop and a batch conversion do not share a
  thread. The conversion runs on a worker and reports back; doing it inline
  freezes the window for the length of the batch, which on a big folder looks
  exactly like a crash.
- **It breaks a claim in `graphify.md`.** The graph currently traverses the whole
  app because there is one process and no runtime bridge. pywebview's `js_api` is
  a string lookup an AST extractor cannot see, so the day this lands, no edge
  will connect the frontend to `image_convertor/`. Fix that section in the same
  change -- `workflow.md` says a stale note is worse than no note, and this one
  would be actively misleading.
- **Keep the CLI.** It is what scripts drive and what the tests exercise. The
  GUI is a second front end, not a replacement.

## 6. A light theme

The same window, in light.

- **Waits on item 5**, and specifically on `design-system.md` being real. A
  theme is a second set of values for tokens the first theme established; if the
  dark theme hardcoded its colours, this item begins by undoing that.
- **Tokens, not a second stylesheet.** One set of CSS custom properties, two
  sets of values, switched at the root. A duplicated stylesheet drifts within a
  week.
- **What it is not.** Not an inversion of the dark palette. Greys that read as
  correct on dark read as dirty on light, and shadows that carry depth on light
  do nothing on dark.
- **Where the choice lives.** The config file from item 4, plus a decision about
  whether to follow the OS setting by default. Follow-the-OS is the better
  default and is one media query, but only if the app also lets it be overridden
  -- the user who picked dark deliberately does not want it reverting at sunrise.

## 7. Several effects on one run -- DONE

Landed first rather than last, for the reason the old entry gave: writing
blur and noise as standalone flags and then retrofitting a list onto them is
most of the work of writing them twice.

`image_convertor/effects.py` holds the effects as frozen values with a `name`
and an `order`; `apply_effects()` deduplicates by kind, keeps the last of
each, sorts by `order` and runs them. `--effect NAME[:VALUE]` is repeatable,
`--effect none` converts with no effects, and `--mode`/`--threshold` still
work as the monochrome effect said the short way.

What was decided rather than deferred:

- **The order is fixed**, not the user's. Most orderings are wrong -- noise
  after a hard cut adds grey to an image with two levels left -- and the app
  knows which. An explicit order is a later flag if it is ever wanted.
- **One of each kind**, last wins, so a front end that lets someone revise an
  answer can append rather than edit.
- **Effects run after the fit**, so a blur radius or a noise amount is in
  output pixels -- the only size the person choosing the number can see.

Still open from the original entry:

- **A single file where a folder is accepted.** `find_images()` still takes a
  folder only.
- **The interactive multi-select.** The CLI still asks only the monochrome
  question, because the CLI is being removed when the GUI lands -- building a
  numbered menu now would be building it to delete it. The GUI is where
  choosing several effects gets a real interface.

- **This is the item that changes the shape of the rest.** Today the pipeline is
  fixed and `--mode` picks one variant of one step. The end state is a list: a
  user chooses blur *and* noise *and* a hard cut, and they run in a defined
  order.
- **Do it before there are many effects, not after.** Retrofitting a list onto
  three or four flags that each grew their own question is most of the work of
  writing them again. If items 1 and 2 are being written anyway, write them into
  this shape from the start.
- **The order question.** Either the user's order, or a fixed sensible one. Fixed
  is the better default -- most orders are wrong (noise after a hard cut adds
  grey to a 1-bit image; blur after it does the same) and the app knows which
  are. Allowing an explicit order is a later flag, not the first version.
- **Two shapes to choose between.** A repeatable flag (`--effect blur:2
  --effect noise:30`), or one comma-separated list. The repeatable flag reads
  better and argparse gives it for free with `action="append"`; the interactive
  side wants a numbered menu that can be answered `1,3` either way.
- **The interactive question has to stay answerable.** The current questions all
  take one answer and have a default on enter. A multi-select must keep both --
  enter means "no effects, convert as-is".
- **Folder or image.** "on an image/folder" in the request: today the input is
  always a folder. Accepting a single file path wherever a folder is accepted is
  a small change in `find_images()` and worth doing here rather than as its own
  item.
