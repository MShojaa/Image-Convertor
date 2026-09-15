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

### Controls

Every input, select and button is `--control-height` tall, `--radius`,
`--surface-raised`, and `1px solid var(--border)`. Focus is a 2px
`--accent` outline with a 2px offset -- an outline rather than a border, so
focus never changes an element's size and nothing shifts when you tab through.

**The focus ring is never removed.** `:focus-visible` is what styles it, so it
appears for the keyboard and not for the mouse, but there is no rule anywhere
that sets `outline: none` without putting something else in its place.

### Buttons

Two kinds. **Primary** is `--accent` with `--accent-text`, and there is exactly
one in the window: Convert. **Secondary** is `--surface-raised` with `--text`
and a border -- Browse, and anything added later.

A disabled button is `--text-faint` on `--surface`, no border change, and
`cursor: default`. Not 50% opacity: opacity on a dark theme makes text that is
still readable but muddy, and the point of disabled is that it reads as
unavailable at a glance.

### The effect rows

One row per effect: a checkbox, the name, and that effect's settings inline,
which go `--text-faint` and non-interactive when the box is clear. The settings
stay visible rather than appearing on tick -- a row that changes height when you
check it moves everything below it, and this list is short enough that showing
all of it costs nothing.

They are listed **in the order they run**, not the order they were added to the
app, because that order is a real thing the user needs to know and a list is the
cheapest place to say it.

### The log

Monospace, `--text-sm`, one line per file, scrolling, with the newest at the
bottom. Three line kinds, and each says which it is in words as well as colour:

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

## What this file does not cover

The window frame, the titlebar and the menu bar are the OS's, and the app does
not draw them. There is no dark-mode titlebar API being used and no frameless
window -- a window with a light titlebar over a dark page looks unfinished, and
the fix for it is a piece of work with its own failure modes that has not been
argued for here.
