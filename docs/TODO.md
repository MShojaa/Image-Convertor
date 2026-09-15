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

## 1. A blur effect -- DONE

`Blur(radius)` in `effects.py`, Pillow's `ImageFilter.GaussianBlur`, no new
dependency. `--effect blur` takes the default 1 pixel, `--effect blur:2.5`
says otherwise. The radius is a float: below 1 is the useful range on a small
image. A radius of 0 is the identity rather than an error, which a slider
starting at zero needs; a negative one is refused.

It runs at order 10, before monochrome, which is the only ordering that does
anything -- a 1-bit image has no levels between black and white left to smear.

The README says which pairing is worth reaching for (blur into a hard cut,
for a soft-edged threshold) and which does nothing (blur into a dither).

## 2. A noise effect -- DONE

`Noise(amount, seed)` in `effects.py`, at order 20 -- after blur, because
blur over noise is just a quieter noise, and before monochrome.

**Uniform, not Gaussian.** One number to expose and one to reason about:
every pixel moves by at most `amount`, either way. Gaussian needs a standard
deviation and still has no bound; film grain is the argument for it, and this
is not a film grain tool.

**The seed defaults to 0, not the clock.** Seeding from the clock is the usual
default and is the wrong one here -- converting the same folder twice has to
give the same files, and a test of unseeded noise can only assert that
something changed. `--effect noise:40:7` picks a different one.

**It is a whole-image operation, not a loop.** The obvious version -- read a
pixel, add a random number, write it back -- is a Python loop per pixel: fine
on an icon, tens of seconds on a photograph. Instead the noise is built as an
image from `Random.randbytes`, scaled to the amount, and added with
`ImageChops.add`, which clamps rather than wrapping -- 250 + 30 has to be
white, not 24. A 4000x3000 image takes about a tenth of a second.

It converts to grey first, because monochrome would throw the colour away
anyway and noising three channels independently makes speckle that grey
averages back out.

## 3. An output format -- DONE

`image_convertor/formats.py`. `--format png|jpg|bmp|gif|tiff|webp`, defaulting
to the source's own format per file, so a png in gives a png out and a mixed
folder stays mixed. `.jpeg` and `.tif` resolve to the same formats as `.jpg`
and `.tiff`; `.ico` reads but cannot be written back at an arbitrary size, so
"the same as the input" falls back to png for those.

**This was the breaking one, and it took the major bump to 2.0.0.** Everything
used to land as `.bmp`; a script globbing `output\*.bmp` now finds nothing.

The separation the old entry asked for is real: the format is the container
and the effects decide the depth. There is no "monochrome bitmap" format,
because it would be a second way to say `--format bmp --effect monochrome`.

**The awkward pair turned out to be worse than expected.** Pillow does not
refuse a 1-bit image saved as JPEG -- it writes 8-bit grey and says nothing,
so a dither comes back ringing with no error anywhere. `formats.refuse_reason`
is what stops it, before the file is written, and the message names the way
out. Nothing else is refused: gif and webp store two levels perfectly well
(webp is forced lossless when the image is 1-bit, since it is lossy by
default and that is JPEG's problem again).

In a batch the refusal fails that one file and the run carries on, which is
how an unreadable file already behaved -- a mixed folder converted to "the
same as the input" should not be stopped by the one jpg in it.

## 4. An option for the input folder -- DONE

The old entry had this right: the mechanism already existed (`--input`,
`base_folder()`), and what was missing was **remembering the answer**. So the
work was the config file, which items 5 and 6 also wanted.

`image_convertor/settings.py`, one JSON file at
`%LOCALAPPDATA%\Image-Convertor\settings.json`. The profile rather than
beside the exe: the install folder is not reliably writable, and a rebuilt or
moved exe would lose everything.

Resolution order for the input folder is now `--input`, then `input\` beside
the app, then the folder used last time, then ask. The remembered one is
checked rather than trusted -- still a folder, still has images -- because it
is the setting most likely to have stopped being true since it was written.

**Every read is defensive, and that is the design.** A settings file can be
hand-edited, half-written by a machine that lost power, or left by a newer
version. None of that raises: a bad file reads as no file, and one bad key
costs only that key. A convenience that refuses to start is worse than no
convenience.

`--no-remember` opts a run out of both reading and writing, for scripts.

Also landed here: `tests/conftest.py` points the settings folder at a tmp
directory for every test automatically. It is autouse because a test that
forgot would write to the developer's own profile and pass, and the next run
would read it back and fail somewhere else entirely -- which is exactly what
happened while writing this.

Still stored but unused: `theme`, which item 6 reads.

## 5. A GUI, with pywebview -- DONE

`UI/index.html`, `UI/style.css`, `UI/app.js`, and `image_convertor/webapi.py`
as the only Python that knows the page exists. `main.py` is now the window and
nothing else.

**`docs/design-system.md` was written first**, as the old entry insisted, and
it earned that: the stylesheet uses nothing but tokens, which is what makes
item 6 a second block of values rather than a second stylesheet.

**BREAKING, and it took the major bump to 3.0.0: the CLI is gone.**
`image_convertor/cli.py` and its 54 tests were deleted. The coverage they
carried that was about behaviour rather than prompts -- folder resolution, a
file that fails mid-batch, the shrink warning, what is remembered -- moved to
`tests/test_webapi.py`. Anything that drove the exe from a script needs
rewriting against the library, which is unchanged and importable.

What the old entry called out, and how it went:

- **The boundary held.** `converter.py` and `effects.py` learned nothing about
  a window. `webapi.py` is the only module that imports in both directions.
- **Threading was necessary.** The batch runs on a worker thread and reports
  each file back through `window.evaluate_js`; inline it would freeze the
  window for the length of the batch, which looks exactly like a crash.
- **Everything crossing the bridge is JSON.** A `Path` arrives on the other
  side as an empty object, silently. Every method returns plain data, and
  failures come back as `{ok: false, error}` rather than raising, because an
  exception in a `js_api` method reaches JavaScript as pywebview's message
  rather than the sentence written here.
- **It broke the claim in `graphify.md`, as predicted**, and that section was
  rewritten in the same change. Measured afterwards: 22 nodes from `UI/`, 377
  from the Python, zero edges between them.

**`UI/` has no test coverage.** There is no JavaScript runner in this project,
so `app.js` is checked by running the app and everything it may ask for is
tested through `webapi.py`. That is a real gap, not an oversight.

One thing worth knowing for anyone driving the window from Python: pywebview's
`evaluate_js` is unreliable for some DOM reads -- `querySelectorAll(...).length`
came back 0 and `element.dataset.name` came back empty for elements that
demonstrably existed, while `getAttribute()` and `outerHTML` on the same
elements were correct. It cost an hour of chasing a bug that was not there.

## 6. A light theme

The same window, in light.

- **Item 5 is done and `design-system.md` is real**, so this is now what it was
  meant to be: a second block redefining the tokens on `:root`. The stylesheet
  hardcodes nothing, so nothing has to be undone first. The empty block and the
  comment saying so are already in `UI/style.css`.
- **The toggle already exists.** The button, `applyTheme()` and `save_theme()`
  are written and the choice is already stored and read back at startup -- it
  flips `data-theme` on the root and today nothing answers to `light`.
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
