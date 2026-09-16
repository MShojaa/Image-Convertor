# TODO

What each feature decided, and what it cost. Not a wish list -- nothing goes
in here that has not been decided.

**All seven are done.** They are kept rather than deleted because what each one
decided, and what it cost, is the part worth having later -- a finished entry
says why it is the way it is, which is the question that comes back. What is
actually outstanding is the short list at the very bottom.

They were done out of order, and the order was the point. Item 7 went first: it
changes the shape items 1 and 2 would have been written in, and retrofitting a
list onto three flags that had each grown their own question is most of the work
of writing them twice. Then 1, 2, 3 and 4, then 5, then 6 -- which was cheap
only because 5 wrote the design system before styling anything.

| # | what | version |
|---|---|---|
| 7 | the effect pipeline | 1.2.0 |
| 1 | blur | 1.3.0 |
| 2 | noise | 1.4.0 |
| 3 | output format | **2.0.0** -- output stopped always being `.bmp` |
| 4 | input folder, and the settings file | 2.1.0 |
| 5 | the window, and the CLI removed | **3.0.0** -- the CLI went |
| 6 | light theme | 3.1.0 |

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

**Two bugs got through to the user, and both showed as Not Responding.**

The first was at startup, and it is the one worth remembering. pywebview
builds its JavaScript proxy by walking `dir()` of the `js_api` object,
skipping underscored names and **recursing into every other non-callable
attribute**. `Api` held `self.window`, so the walk went into the pywebview
Window, into `window.native`, and down through WinForms until Python's
recursion limit -- on the GUI thread, before the page's first call returned.
The window painted, the page stayed half-built (no formats, no effects, no
folder) and the titlebar said Not Responding. Every attribute on `Api` is now
underscored and the window arrives through `attach()`; the reason is written
in the class, because the next attribute someone adds is how it comes back.

It was invisible from source, where the same recursion is logged and survived,
and only fatal frozen -- so the tests, which drive `Api` directly, could never
have caught it. What catches it now is a test that runs pywebview's own
traversal rule over a real `Api`, plus one asserting nothing public on the
class is anything but a method.

The second: `choose_folder` opened the native
dialog from inside the `js_api` call. A `js_api` method runs while the page
awaits its result and `create_file_dialog` waits on the GUI thread, so the two
waits point at each other -- the window locks up, no dialog ever appears, and
Windows paints it Not Responding. Nothing is logged, because nothing fails. It
now runs on its own thread and the answer comes back as a `folder_chosen`
event, like everything else the app does in the background. Fixed in 3.1.1.

It reached a user because the tests used a fake window that answered instantly
and the real Browse button was never clicked in a real window -- the one path
the GUI work never exercised end to end. `test_webapi.py` now asserts the rule
rather than the symptom: the dialog must not open on the thread that asked for
it.

Also worth knowing for anyone driving the window from Python: pywebview's
`evaluate_js` is unreliable for some DOM reads -- `querySelectorAll(...).length`
came back 0 and `element.dataset.name` came back empty for elements that
demonstrably existed, while `getAttribute()` and `outerHTML` on the same
elements were correct. It cost an hour of chasing a bug that was not there.

## 6. A light theme -- DONE

A second block of the same token names in `UI/style.css`, and nothing else --
which is what writing `design-system.md` first bought.

- **Not an inversion.** No token shares a value between the themes. The accent
  had to get darker rather than lighter: `#5b9dd9` is 2.6:1 on white, fine as a
  block behind dark text and unreadable as the focus ring and button text it is
  also used for.
- **The depth rule flips**, as the old entry predicted: on light the sunken
  surface is the grey one and the raised one is white.
- **The OS is followed by default.** The stored setting is `system`, `dark` or
  `light`, with `system` the default and resolved in JavaScript rather than by a
  media query -- a query would need a second copy of the light tokens, and the
  one rule holding the design together is that there is one block of values per
  theme. The `matchMedia` listener re-resolves only while the choice is
  `system`, so a deliberate choice sticks.

`tests/test_theme.py` parses the stylesheet and checks the rules that cannot be
seen by looking: that both themes define the same tokens, that nothing outside
those blocks names a colour, that the depth rule flips, and that every
foreground clears WCAG AA on every surface it appears on.

That last one earned itself immediately. Two light values looked right and
failed against the **sunken** surface -- the log's background, where the state
colours are used and nowhere else -- at 4.35:1 and 2.92:1. Both were darkened.

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

Since then, and not from the seven: the window gained an **output folder**
beside the input one, so the results no longer have to land next to the app.
Writing into the folder being read is refused rather than allowed -- the results
are images in the input folder, so the next run converts its own output, and
with "same as the input" the run after that overwrites the originals. An
unwritable destination is refused up front too, because it is the same answer
for every file in the batch and by the time a save fails the work is done.

Transparency stopped being thrown away at the door. The app used to composite
every image onto white as the very first thing it did, which made "leave the
clear area alone" impossible to ask for -- by the time an effect ran there was
no clear area left. Alpha now survives the whole pipeline and is flattened at
the end, by `formats.save`, and only when the format cannot hold it. That
changed what every existing conversion of a transparent image produces, so it
took the major bump to 4.0.0.

Still open, and now the only thing left in this file:

- **A single file where a folder is accepted.** `find_images()` takes a folder
  only, so "on an image/folder" from the original request is half done. It is a
  small change there plus a Browse button that can pick either, and it did not
  belong in any of the seven.

The interactive multi-select the old entry wanted is done, and not as a numbered
menu: the window lists the effects in the order they run, each with a checkbox
and its own settings inline, and the settings stay visible when the box is clear
rather than appearing on tick -- a row that changes height when checked moves
everything below it.
