# Design system

What the window looks like, written down before it was styled. The order
matters: a stylesheet written first becomes the spec by accident, and then
nobody can change a colour without checking six places to see what else it
meant.

Everything here is a CSS custom property on `:root` in `UI/style.css`. **Nothing
in the stylesheet may hardcode a colour, a radius, or a spacing** -- if a value
is not in this file, the answer is to add it here first. That rule is what makes
the light theme in `TODO.md` item 6 a second set of values rather than a second
stylesheet.

Dark is the design, not the variant. Light comes later and is not an inversion
of this -- see [Two themes](#two-themes).

## The mark

`assets/make_icon.py` draws it, and the results are committed so a build does
not have to run it. The design is the thing the app does: sun and hills -- the
glyph everything uses for "image" -- with the right half of the same picture run
through the app's own `Monochrome` effect. The right side of the icon is real
output, not an impression of one, and the sun sits on the seam so each half
shows half of the same subject rather than two pictures.

Three things it got wrong first, all of which only show at small sizes:

- **The dither has to be coarse.** Dithering a smooth picture at full resolution
  looks like the picture -- correct, and invisible. The right half is dithered
  at a twelfth of the size and scaled back with NEAREST.
- **The tile and the picture are supersampled; the dither is not.** Pillow does
  not antialias a rounded rectangle or a polygon. Scaling a dither down averages
  it back into the grey it came from, so it is computed at the final size.
- **There is a seam down the middle.** Without it the halves blend and the icon
  is just a picture.

The `.ico` carries 16 through 256 so Windows never scales one, and the header
shows the same mark at 28px from a 96px PNG. `tests/test_icon.py` checks each
size is really in the file, that none came out blank, and that the right half
still has fewer levels than the left -- which is how a dither that stopped being
applied would be noticed.

**On Windows the window icon is the exe's icon.** pywebview's own `icon=` is
GTK/QT only, so `build.py` passes `--icon` to PyInstaller and that is the whole
story -- which is also why running from source shows Python's icon instead.

## Colour

Three greys for surfaces, three for text, one accent, three states. That is the
whole palette, and it is small on purpose: a palette with a colour for every
occasion produces a window where nothing is emphasised because everything is.

### Surfaces

| token | value | what it is |
|---|---|---|
| `--surface-sunken` | `#141517` | the window behind everything; the darkest thing on screen |
| `--surface` | `#1c1e21` | panels, the file list, anything sitting on the window |
| `--surface-raised` | `#26292e` | inputs, the things you can click into |
| `--border` | `#33373d` | the line between two surfaces, when one is needed |
| `--border-strong` | `#454a52` | a border that has to be seen: a focused input |

Three levels and no more. Depth here comes from the surface getting *lighter*
as it comes forward, which is how a dark interface does it -- shadows are
invisible on near-black, so a raised panel that is the same colour as the one
under it with a shadow between them reads as flat.

### Text

| token | value | what it is |
|---|---|---|
| `--text` | `#e6e8ea` | body text, filenames, numbers |
| `--text-dim` | `#9aa1a9` | labels, units, anything explaining something else |
| `--text-faint` | `#6b727a` | disabled, placeholder, the parts of a path that are not the end |

Not white. `#ffffff` on `#141517` is a contrast ratio of about 17:1, which is
past the point of being readable and into the range where the text buzzes
against the background on an OLED panel. `--text` is around 13:1 -- still far
above the 4.5:1 that WCAG AA asks for body text, and easier to look at for the
length of a batch.

`--text-dim` on `--surface` is about 6:1 and `--text-faint` about 3.4:1. The
faint one is **below AA for body text and is only ever used for text that is
also said another way** -- a disabled control, a placeholder repeating its own
label, the middle of a path whose end is what matters.

### Accent

| token | value | what it is |
|---|---|---|
| `--accent` | `#5b9dd9` | the primary button, focus rings, the progress bar |
| `--accent-hover` | `#72adde` | that, hovered |
| `--accent-text` | `#0d1117` | text *on* the accent -- dark, because the accent is light |

One accent. The Convert button is the only primary action in the window, so it
is the only thing that gets it.

### States

| token | value | what it is |
|---|---|---|
| `--good` | `#5cb176` | a run that finished with nothing to report |
| `--warn` | `#d6a14a` | the "could not shrink" warnings, and refused pairings |
| `--bad` | `#d97070` | a file that failed |

Muted rather than saturated, for the same reason the text is not white: a pure
red on a near-black panel vibrates. These are the only three colours in the
window that carry meaning by being a colour, so each one is also said in words
-- a count, a filename, a sentence. Nothing in this app is communicated by
colour alone.

## Type

One family, four sizes, three weights.

| token | value | for |
|---|---|---|
| `--font` | `system-ui, "Segoe UI Variable", "Segoe UI", sans-serif` | everything |
| `--font-mono` | `"Cascadia Mono", "Consolas", ui-monospace, monospace` | paths, filenames, sizes |
| `--text-lg` | `1.0625rem` (17px) | the one heading in the window |
| `--text-base` | `0.875rem` (14px) | body, buttons, inputs |
| `--text-sm` | `0.8125rem` (13px) | labels, the log |
| `--text-xs` | `0.75rem` (12px) | units, counts |
| `--weight-normal` | `400` | body |
| `--weight-medium` | `500` | labels, buttons |
| `--weight-bold` | `600` | the heading |

System fonts, deliberately: this is a Windows desktop tool and it should look
like one. A webfont would be a download, a flash of unstyled text, and one more
thing to get into the frozen build.

**Filenames and sizes are monospace.** A list of files scanned down the left
edge is easier to read when the characters line up, and `128x64` next to
`1280x640` is a mistake waiting to happen in a proportional font.

## Space

A 4px scale. Every margin, padding and gap in the stylesheet is one of these.

| token | value |
|---|---|
| `--space-1` | `4px` |
| `--space-2` | `8px` |
| `--space-3` | `12px` |
| `--space-4` | `16px` |
| `--space-5` | `24px` |
| `--space-6` | `32px` |

Not a continuous scale -- six steps, and anything that does not fit one of them
is a layout that has not been decided yet.

## Shape

| token | value | for |
|---|---|---|
| `--radius` | `6px` | inputs, buttons, panels |
| `--radius-sm` | `4px` | chips, the progress bar |
| `--control-height` | `32px` | every input, select and button |

One height for every control is what makes a row of them line up without a
single per-control adjustment.

## Motion

| token | value | for |
|---|---|---|
| `--fast` | `120ms` | hover, focus, a button press |
| `--slow` | `240ms` | a panel appearing, the log scrolling |

Both `ease-out`. Nothing in this window animates for longer than that, and
nothing animates position -- a control that slides is a control you wait for.

**All of it is off under `prefers-reduced-motion`.** One media query at the
bottom of the stylesheet sets every duration to `0.01ms`, which is the
documented way to do it without breaking transition-end handlers.

## The components

### Browse

The button disables itself while the folder dialog is open and re-enables when
it closes. The dialog is modal and the page is not, so without that a second
click opens a second dialog behind the first.

### The folders panel

Both folders live in one panel, because they are the same question asked twice
and a heading between them costs a row of height to say so. The labels share a
5.5rem column so the two paths start at the same x and read as a pair, and each
hint is indented to sit under its path rather than under its label.

The output folder has a **Default** button next to Browse. Typing a path is how
you get away from the default; without that button there is no way back to it
short of retyping it, and it is the one path the user never chose.

### Controls

Every input, select and button is `--control-height` tall, `--radius`,
`--surface-raised`, and `1px solid var(--border)`. Focus is a 2px
`--accent` outline with a 2px offset -- an outline rather than a border, so
focus never changes an element's size and nothing shifts when you tab through.

**The focus ring is never removed.** `:focus-visible` is what styles it, so it
appears for the keyboard and not for the mouse, but there is no rule anywhere
that sets `outline: none` without putting something else in its place.

### The theme switcher

A pill with three choices in it -- system, light, dark, as a monitor, a sun and
a moon -- with the chosen one ringed. **All three are on screen at once**, so
which theme is set and what the alternatives are can both be read without
pressing anything.

It replaced a single button that cycled through the three. Two things were
wrong with that: from a dark desktop the first press picked "dark" and nothing
appeared to change, and getting back to "system" meant pressing until it came
round again. Here "system" is one of the three, so following the desktop is a
click like any other rather than a state you fall out of.

**It is a radiogroup**, because that is what it is: one of three. The group is a
single tab stop with a roving `tabindex`, and the arrow keys move within it --
three separate tab stops for one setting would be three times the tabbing for
no more choice. Each icon carries its name in a `visually-hidden` span and a
`title`, since an icon alone says nothing to a screen reader.

The ring on the chosen one is a border plus a lifted surface, not just a
brighter colour. The unchosen two are already a colour apart, and three shades
of the same idea does not read as a state.

### Buttons

Two kinds. **Primary** is `--accent` with `--accent-text`, and there is exactly
one in the window: Convert. **Secondary** is `--surface-raised` with `--text`
and a border -- Browse, and anything added later.

A disabled button is `--text-faint` on `--surface`, no border change, and
`cursor: default`. Not 50% opacity: opacity on a dark theme makes text that is
still readable but muddy, and the point of disabled is that it reads as
unavailable at a glance.

### The effect rows

**A fixed name column, then that effect's settings flowing after it.** One grid
across the whole list was the first answer to lining the inputs up, and it
aligned them and then overflowed: the column count came from the widest effect,
and five columns of settings do not fit the panel -- `transparent` had its
tolerance and soft edges off the side of the window, behind a scrollbar. The
fixed column keeps what the alignment was for, since every row's settings start
at the same x, and past it they wrap, which is the part a shared grid cannot do.

A row is a step number, a checkbox and name, then those settings as
label/control pairs. **The control matches the setting**: a dropdown for a fixed
set of words, a checkbox for a yes/no, a box to type in otherwise. Each one
still produces the same text the effect would be typed as, so the two ways in
cannot drift apart. A dropdown sizes to its longest option rather than to the
width the typed boxes use -- "tolerance" does not fit in 5rem and came out as
"tolera".

**A picked row is tinted and its number takes the accent**, so what the run will
do reads off the panel at a glance rather than by checking five boxes.

A setting the chosen mode does not use is greyed rather than hidden -- a row
that changes shape when you use it moves everything below it. The one case today
is the tolerance, which an exact match ignores. The settings go `--text-faint`
when the box is clear but stay visible, for the same reason.

They are listed **in the order they run**, and numbered with it, because that
order is a real thing the user needs to know and the list is the cheapest place
to say it. Under the list, a line spells out what the current selection will
actually do: `Will run: blur -> monochrome`. **A setting left at its default is
written as nothing** there, the same rule the Python side follows when it
describes an effect -- otherwise that line reads
`transparent::tolerance::no -> monochrome::white`, which is noise.

### The log

Monospace, `--text-sm`, one line per file, scrolling, with the newest at the
bottom.

**It is the panel that grows.** Everything above it is as tall as its contents
and the run panel takes what is left, so making the window bigger makes the log
bigger rather than making the gaps bigger. Its `min-height` is a floor, not a
target. The panels are deliberately tight for the same reason: every pixel of
padding above is a pixel the log does not get. Three line kinds, and each says which it is in words as well as colour:

- a plain conversion: `--text-dim`
- a warning (`WARNING  ...`): `--warn`
- a failure (`FAILED  ...`): `--bad`

It is the CLI's output, in a box. That is deliberate -- it is the one part of
the old interface that was genuinely good, and a progress bar with no detail
behind it is worse at the only moment it matters, which is when something went
wrong with one file out of two hundred.

### Progress

A 4px bar in `--accent` on `--surface-raised`, with a count beside it
(`34 / 200`). The bar alone cannot say how far through a long batch it is with
any precision, and the count alone has no shape -- they are two halves of one
control and neither ships without the other.

## Two themes

Both are written, as two blocks of the same token names in `UI/style.css`. The
three rules this file set out before either existed all held:

1. **Every value is a token and the stylesheet only uses tokens.** Enforced by
   `tests/test_theme.py`, which strips the two token blocks and fails on any
   hex value, named colour or `rgb()` left in what remains.
2. **The light theme is not an inversion.** No token has the same value in both.
   The accent is the clearest case: `#5b9dd9` is 2.6:1 on white, fine as a block
   behind dark text and nowhere near readable as the focus ring and button text
   it also has to be, so light uses `#2a6fb0`.
3. **The depth rule flips.** On dark the raised surface is the lightest; on
   light the sunken one is the grey and the raised one is white, with borders
   doing the work shadows do elsewhere. Also asserted, in both directions.

### Three choices, two looks

The stored setting is `system`, `dark` or `light`, and **`system` is the
default** -- an app that ignores the OS setting is the odd one out. It is a
stored choice like the other two rather than the absence of one, so the button
cycles through all three and the label says which, resolving to `System (dark)`
so the current look is never a guess.

`system` is resolved **in JavaScript, not in CSS**. A media query would need a
second copy of the light tokens to cover the system case, and rule 1 above is
the whole design. `applyTheme()` resolves the choice and stamps `data-theme`,
and a `matchMedia` listener re-resolves when the OS changes -- **only while the
choice is `system`**, because someone who picked dark deliberately does not want
it reverting at sunrise.

### Contrast is measured, not asserted

Every ratio quoted in this file is computed in `tests/test_theme.py` from the
values as written. Body text and the state colours must clear 4.5:1 on every
surface they appear on, and `--text-faint` -- documented above as below that and
only used where the same thing is said another way -- must still clear 3:1.

The surface that matters is the **sunken** one: the log sits on it, and the
three state colours are used nowhere else. Two light values were chosen, looked
correct, and failed there at 4.35:1 and 2.92:1. They were darkened. That is what
the test is for.

## The page never scrolls

`#app` is a fixed-height flex column and the log is the part that scrolls
inside it. The height is `100%` of `html`/`body`, **not `100vh`**: at 125%
display scaling `100vh` computes to a fraction of a pixel more than the
viewport and rounds up, which is one pixel of overflow and a scrollbar down the
whole window to show it. That is not a hypothetical -- it is what the window
did, and the fix is the percentage.

## Two columns

Past **62rem** the controls and the log sit side by side; below it they stack.
That breakpoint is not a taste decision. Height is the scarce dimension -- a
1080p screen at 125% scaling is 864 logical pixels tall and 1536 wide -- so the
layout turns spare width into log height, and the log goes from six lines to
about twenty-seven at the default size.

Both columns can shrink and each scrolls inside itself. The run panel has a
floor (`min-height: 12rem`) so a short window shrinks the controls rather than
collapsing the panel and spilling the Convert button out of the bottom, which
is exactly what happened when it had none.

## The window's size

`main.py` decides it, and the numbers are measured rather than picked. The
controls come to 684px with the log at its 6rem minimum; the log is one line
per file and the only place a warning is explained, so it gets 240px rather
than its minimum. That plus the window chrome is where 960 comes from, and the
width is the widest row (786px) with slack for a long path.

**The screen wins when it is smaller**, and the two are measured in different
units -- which was a real bug and the reason the window scrolled. `create_window`
takes logical pixels, the same ones CSS uses; `webview.screens` reports physical
ones. At 125% scaling a 1920x1080 screen is 1536x864 logical, so asking for a
940-tall window was asking for 1175 physical pixels on a screen with 1080.
Windows clamped it, the page opened shorter than it needed, and it scrolled.

`window_size()` divides the screen by `display_scale()` before comparing, and
`tests/test_window.py` checks the arithmetic on a range of screens and scalings.

## What this file does not cover

The window frame, the titlebar and the menu bar are the OS's, and the app does
not draw them. There is no dark-mode titlebar API being used and no frameless
window -- a window with a light titlebar over a dark page looks unfinished, and
the fix for it is a piece of work with its own failure modes that has not been
argued for here.
