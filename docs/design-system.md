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

Four greys for surfaces, three for text, one accent, three states. That is the
whole palette, and it is small on purpose: a palette with a colour for every
occasion produces a window where nothing is emphasised because everything is.

The accent appears twice more as itself at low alpha -- a tint and a ring --
rather than as two further blues. Both are written in terms of the accent, so
changing the hue changes every place it is used at once.

### Surfaces

| token | value | what it is |
|---|---|---|
| `--surface-sunken` | `#0e1013` | the window behind everything; the log and the chain strip |
| `--surface` | `#17191e` | panels, anything sitting on the window |
| `--surface-raised` | `#1f232a` | inputs, the things you can click into |
| `--surface-hover` | `#262b33` | a row or a quiet button under the pointer |
| `--border` | `#282d35` | the line between two surfaces, when one is needed |
| `--border-strong` | `#3c444f` | a border that has to be seen: a hovered input, a scrollbar |
| `--edge-light` | `rgba(255,255,255,0.05)` | the lit top pixel of a panel |

Four levels and no more, and the fourth is a state rather than a layer. Depth
here comes from the surface getting *lighter* as it comes forward, which is how
a dark interface does it -- shadows are invisible on near-black, so a raised
panel that is the same colour as the one under it with a shadow between them
reads as flat.

`--edge-light` is the other half of that. A one-pixel highlight across the top
of a panel is what a light source above the window would leave, and it is the
only thing on dark that makes a card look lifted rather than outlined. It goes
fully transparent on light, where shadows work and a white highlight on white
would be invisible anyway.

### Text

| token | value | what it is |
|---|---|---|
| `--text` | `#e9ebee` | body text, filenames, numbers |
| `--text-dim` | `#9aa2ac` | labels, units, anything explaining something else |
| `--text-faint` | `#6b7380` | disabled, placeholder, the parts of a path that are not the end |

Not white. `#ffffff` on `#0e1013` is a contrast ratio of about 19:1, which is
past the point of being readable and into the range where the text buzzes
against the background on an OLED panel. `--text` is around 14:1 -- still far
above the 4.5:1 that WCAG AA asks for body text, and easier to look at for the
length of a batch.

`--text-dim` on `--surface` is about 6:1 and `--text-faint` about 3.4:1. The
faint one is **below AA for body text and is only ever used for text that is
also said another way** -- a disabled control, a placeholder repeating its own
label, the middle of a path whose end is what matters.

### Accent

| token | value | what it is |
|---|---|---|
| `--accent` | `#5aa2f5` | the primary button, focus rings, the progress bar, the heading rules |
| `--accent-hover` | `#7bb5f8` | that, hovered; and the far end of the progress bar |
| `--accent-text` | `#0b1220` | text *on* the accent -- dark, because the accent is light |
| `--accent-soft` | the accent at `0.14` | the tint behind a ticked effect, the chosen theme, the corner wash |
| `--accent-ring` | the accent at `0.32` | the halo on a focused control, the border of a tinted thing |

One accent. The Convert button is the only primary action in the window, so it
is the only thing that gets it *solid* -- and the only thing wearing
`--shadow-accent`, which is what makes the glow mean "this is the button".

The two alpha tokens are the accent doing the work a second and third grey used
to do: a ticked effect row, the chosen theme button, a focus halo. Because they
are the accent rather than beside it, nothing has to be re-picked when the hue
changes; and because they are alpha rather than mixed, they sit correctly on
whichever surface they land on in either theme.

### States

| token | value | what it is |
|---|---|---|
| `--good` | `#5ec08a` | a run that finished with nothing to report |
| `--warn` | `#e0b054` | the "could not shrink" warnings, and refused pairings |
| `--bad` | `#ec7f7f` | a file that failed |

Muted rather than saturated, for the same reason the text is not white: a pure
red on a near-black panel vibrates. These are the only three colours in the
window that carry meaning by being a colour, so each one is also said in words
-- a count, a filename, a sentence. Nothing in this app is communicated by
colour alone. In the log each kind also carries a two-pixel bar down its left
edge, so a scrolled-back run shows *where* the trouble is as a shape before any
of it is read.

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
| `--weight-medium` | `500` | buttons |
| `--weight-bold` | `600` | the heading, the panel labels |
| `--track-label` | `0.06em` | the tracking on an uppercase panel label |

System fonts, deliberately: this is a Windows desktop tool and it should look
like one. A webfont would be a download, a flash of unstyled text, and one more
thing to get into the frozen build.

Panel labels are 12px uppercase, bold, and tracked out by `--track-label`.
Uppercase text set at its default spacing reads as a block rather than as
words, and at this size a label needs to be scannable more than it needs to be
large. The heading, the only line of big type in the window, goes the other way
with slightly negative tracking -- default spacing looks loose beside the tight
labels under it.

**Filenames and sizes are monospace.** A list of files scanned down the left
edge is easier to read when the characters line up, and `128x64` next to
`1280x640` is a mistake waiting to happen in a proportional font.

## Space

A 4px scale. Every margin, padding and gap in the stylesheet is one of these.

**Height is the scarce one, and the scale is not the budget.** A 1080p laptop
at 125% scaling is 864 logical pixels tall and `main.py` sizes the window for
it; every vertical pixel a panel spends is a pixel the log does not get. The
refresh learned this the expensive way -- moving the panels from `--space-2` to
`--space-3` padding and gaps, one step on the scale, put 852px of controls into
708px of room at that window size and hung a scrollbar down the one column that
should never need one. The panels are back at `--space-2` vertically. Colour,
shape and state carry the look; padding does not.

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
| `--radius` | `10px` | panels |
| `--radius-sm` | `7px` | inputs, buttons, effect rows, the log |
| `--radius-pill` | `999px` | the theme switcher, the progress bar, scrollbars |
| `--control-height` | `34px` | every input, select and button |

One height for every control is what makes a row of them line up without a
single per-control adjustment. 34px rather than 32 because a 14px label inside
a 32px box leaves four pixels above and below, which is the difference between
a control and a cell in a table.

Two radii, not one: the container is rounder than the things inside it. A panel
and its inputs at the same radius read as one nested box; ten against seven
reads as a card with contents in it. `--radius-pill` is for the things that are
genuinely round -- a segmented control, a bar, a scrollbar thumb -- and never
for a box.

### Shadow

| token | for |
|---|---|
| `--shadow-sm` | the resting lift on a panel, the switcher, the logo |
| `--shadow-accent` | the Convert button, and only that |

Two, and there is no third: nothing in this window floats over anything, so a
token for that was written, used nowhere, and taken out again.

Defined per theme, not shared. On dark a shadow is nearly invisible and only
softens an edge, so `--edge-light` does the lifting; on light the shadow *is*
the lifting and the highlight is switched off. Both sets live in their theme
block for that reason.

## Motion

| token | value | for |
|---|---|---|
| `--fast` | `120ms` | hover, focus, a button press |
| `--slow` | `240ms` | the progress bar advancing |
| `--ease` | `cubic-bezier(0.2, 0.8, 0.3, 1)` | all of it |

One curve, and it leaves fast and settles slow. That is the difference between
a control that moves and one that responds -- a plain `ease-out` starts gently,
which at 120ms reads as lag.

Nothing in this window animates for longer than 240ms, and the only thing that
animates position is a button moving one pixel down while it is held, which is
a press rather than a transition. A control that slides is a control you wait
for.

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

### The titlebar

**The window has no OS titlebar.** `main.py` passes `frameless=True`, and the
bar across the top of the page is the only one there is: the app's own colour
all the way to the top edge, rather than a strip of someone else's chrome above
a dark page.

It is 32px, `--surface`, with a border under it. The left half carries the mark
and the name and is the **drag region** -- `pywebview-drag-region`, which is
what pywebview moves the window from. The right half carries the theme switcher
and then the window buttons, and is deliberately *not* draggable: a button you
can accidentally drag the window with is a button that sometimes does nothing.

Double-clicking the drag region maximizes, because every other window on this
desktop does and the one that does not feels broken rather than minimal.

**The buttons are 46px wide and the full height of the bar**, which is what
Windows uses: maximized, the target reaches the very corner of the screen, and
a corner is the easiest thing on a screen to hit. Minimize, maximize, close, in
that order, for the same reason.

Full height is easy to write down and easy to lose. `align-items: center` on
the actions strip made the row of buttons as tall as its own content -- 12px of
icon -- so they were 46x12 in a 32px bar, floating in the middle of it and
touching no edge at all. The strip stretches; the switcher centres itself.

**The glyphs are 12px on a 1px stroke**, on the half-pixel coordinates their
paths already use. They were 1.1, which straddles two device pixels at 125%
scaling: soft glyphs next to the crisp ones Windows draws on every other
window, which reads as wrong rather than as different.

**A caption button lets go of focus when the pointer presses it.** Clicking
maximize left the button focused, and the window returning from the resize is
enough for Chromium to call that focus visible -- so a ring sat on the button
until something else was clicked, which no other window on this desktop does.
`event.detail` is how the press arrived: a mouse click counts clicks, a
keyboard activation reports 0. The pointer drops focus, the keyboard keeps it.
The ring itself is 1px, inset -- a caption button is chrome, and the 2px accent
box a form control wears reads as a selected cell up here.

**Close goes red on hover, and that red is the same in both themes.** It is the
one place a fixed colour is right -- every other window on this desktop has a
red close button, and matching the convention is worth more than being
internally consistent. `tests/test_theme.py` knows about the exemption and
would make anyone adding a second one say why.

The maximize button draws a square or two stacked squares, and **which one
follows the window rather than the click** -- a window maximized by Aero Snap,
a drag to the top edge, or Win+Up draws the right one too, because the page
asks after every resize rather than remembering what it last did.

### Three things framelessness breaks

All measured, and all in `image_convertor/window_frame.py` with the numbers:

- **The resize border goes with the titlebar.** `FormBorderStyle.None` leaves
  the window without `WS_THICKFRAME`, and a hit test on the corner comes back
  `HTCLIENT` -- nothing to drag, so the window cannot be resized at all. Adding
  that one style bit back, with the caption still off, restores every edge.
- **A borderless window maximizes over the taskbar**, because Windows hands a
  bordered window the work area and a borderless one the whole screen. Measured
  at 1928x1088 against a work area of 1920x1020 -- the bottom 68 pixels,
  including the Convert button, behind the taskbar. `MaximizedBounds` fixes it.
- **That bound is per monitor**, so it is set again whenever the window moves.
- **The style bit that restores the edges also draws them.** The grab areas are
  invisible, but DWM still draws the window's border around them -- a line
  outside a window that is otherwise the app's own colour to its edge.
  `DWMWA_BORDER_COLOR` set to `DWMWA_COLOR_NONE` turns it off. Windows 11 or
  nothing: on 10 the attribute is unknown, the call fails, and the border stays.

### The theme switcher

A pill with three choices in it -- system, light, dark, as a monitor, a sun and
a moon -- with the chosen one ringed. **All three are on screen at once**, so
which theme is set and what the alternatives are can both be read without
pressing anything.

**It is 24px, not `--control-height`.** It used to be a form control in a page
header beside the panels, and it kept that height when it moved into the
titlebar -- where `--control-height` is 34px and the bar is 32, so the pill hung
a pixel above the top edge of the window and a pixel through the bar's own
bottom border. Up here it is chrome and it sizes to the bar. The lesson is the
general one: `--control-height` is the height of a control in a panel, and the
titlebar is not a panel.

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
   The accent is the clearest case: `#5aa2f5` is 2.4:1 on white, fine as a block
   behind dark text and nowhere near readable as the focus ring and button text
   it also has to be, so light uses `#1f6feb`.
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

The menu bar -- there isn't one -- and the window's drop shadow, which Windows
draws. Everything else inside the window is here.
