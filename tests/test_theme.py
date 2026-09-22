"""The stylesheet, checked against the rules in docs/design-system.md.

Three things are asserted here, and each is a rule that is easy to break by
accident and impossible to notice by looking:

1. **The two themes define the same tokens.** A token added to one and not the
   other leaves that theme falling back to the other's value, which on a dark
   colour in a light window is invisible in review and obvious to a user.
2. **Text meets WCAG AA against the surface it sits on.** The numbers in the
   design system are measured, not asserted, and this is where they are
   measured. The log's background is the *sunken* surface, which is the one
   that nearly got missed: three colours are used only there.
3. **Nothing outside the token blocks hardcodes a colour.** That is the single
   rule holding the whole system together -- the light theme is a second set of
   values only because the stylesheet never names a colour directly.

No browser is involved. These are the values as written, which is what the
browser would resolve them to.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STYLESHEET = Path(__file__).resolve().parent.parent / "UI" / "style.css"
CSS = STYLESHEET.read_text(encoding="utf-8")

AA_BODY = 4.5      # WCAG AA, body text
AA_LARGE = 3.0     # WCAG AA, large text -- and the floor for anything visible


def tokens(selector: str) -> dict[str, str]:
    """The colour tokens defined in one block."""
    found = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", CSS, re.S)
    assert found, f"no {selector} block in the stylesheet"
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", found.group(1)))


DARK = tokens(":root")
LIGHT = tokens('[data-theme="light"]')
THEMES = {"dark": DARK, "light": LIGHT}


def luminance(colour: str) -> float:
    """Relative luminance, per WCAG 2.1."""
    channels = (int(colour[index:index + 2], 16) / 255 for index in (1, 3, 5))
    adjusted = [
        value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * adjusted[0] + 0.7152 * adjusted[1] + 0.0722 * adjusted[2]


def contrast(foreground: str, background: str) -> float:
    first, second = luminance(foreground), luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


# --- the two themes agree --------------------------------------------------

def test_both_themes_define_the_same_colours():
    assert set(DARK) == set(LIGHT)


#: Tokens that are deliberately the same in both themes. The close button's
#: red is a platform convention rather than a theme colour -- Windows draws it
#: the same in its own light and dark themes, and matching that is worth more
#: than being internally consistent. Anything added here needs that kind of
#: reason; the test below is what asks for one.
SHARED_ON_PURPOSE = {"--danger", "--danger-text"}


def test_the_light_theme_is_not_the_dark_one():
    """Every colour is chosen for its theme; none is left behind by accident."""
    shared = {name for name in DARK if DARK[name] == LIGHT[name]}
    assert shared <= SHARED_ON_PURPOSE, (
        f"identical in both themes: {sorted(shared - SHARED_ON_PURPOSE)}"
    )


def test_the_shared_tokens_are_actually_shared():
    """If one stops being shared, the exemption above should go with it."""
    for name in SHARED_ON_PURPOSE:
        assert DARK[name] == LIGHT[name], f"{name} no longer needs exempting"


def test_each_theme_declares_its_colour_scheme():
    """Without it the browser paints form controls and scrollbars for the other."""
    assert "color-scheme: dark" in CSS
    assert "color-scheme: light" in CSS


# --- contrast ---------------------------------------------------------------

@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("surface", ["--surface", "--surface-sunken", "--surface-raised"])
@pytest.mark.parametrize("text", ["--text", "--text-dim"])
def test_body_text_meets_aa_on_every_surface(theme, surface, text):
    palette = THEMES[theme]
    ratio = contrast(palette[text], palette[surface])

    assert ratio >= AA_BODY, f"{theme}: {text} on {surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("state", ["--good", "--warn", "--bad"])
def test_the_state_colours_meet_aa_where_they_are_used(theme, state):
    """They appear in the summary (on --surface) and the log (on --surface-sunken)."""
    palette = THEMES[theme]

    for surface in ("--surface", "--surface-sunken"):
        ratio = contrast(palette[state], palette[surface])
        assert ratio >= AA_BODY, f"{theme}: {state} on {surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_the_faint_text_clears_the_large_text_floor(theme):
    """Documented as below AA for body text and only used where the same thing
    is said another way -- but it still has to be visible."""
    palette = THEMES[theme]

    for surface in ("--surface", "--surface-sunken"):
        ratio = contrast(palette["--text-faint"], palette[surface])
        assert ratio >= AA_LARGE, f"{theme}: --text-faint on {surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_text_on_the_accent_meets_aa(theme):
    """The primary button, which is the one control with text on a colour."""
    palette = THEMES[theme]
    ratio = contrast(palette["--accent-text"], palette["--accent"])

    assert ratio >= AA_BODY, f"{theme}: --accent-text on --accent is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_the_accent_is_visible_as_a_focus_ring(theme):
    """It is drawn as a line on the surface, not as a block behind text."""
    palette = THEMES[theme]
    ratio = contrast(palette["--accent"], palette["--surface"])

    assert ratio >= AA_LARGE, f"{theme}: --accent on --surface is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_the_borders_are_visible_against_their_surfaces(theme):
    """A border nobody can see is a panel that has no edge."""
    palette = THEMES[theme]

    assert contrast(palette["--border"], palette["--surface"]) > 1.1
    assert contrast(palette["--border-strong"], palette["--surface-raised"]) > 1.3


# --- the rule the whole system rests on ------------------------------------

def rules_outside_the_token_blocks() -> str:
    """The stylesheet with the :root and [data-theme] blocks removed."""
    stripped = CSS
    for selector in (":root", '[data-theme="light"]'):
        found = re.search(re.escape(selector) + r"\s*\{.*?\n\}", stripped, re.S)
        stripped = stripped.replace(found.group(0), "")
    return stripped


def test_no_rule_outside_the_token_blocks_names_a_colour():
    """The one rule that makes a second theme a block of values, not a rewrite."""
    body = rules_outside_the_token_blocks()
    # Strip comments first: they quote hex values when explaining a choice.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)

    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b", body)
    named = re.findall(r":\s*(?:white|black|red|green|blue)\b", body)
    functions = re.findall(r"\b(?:rgba?|hsla?)\s*\(", body)

    assert not literals, f"hardcoded colours: {literals}"
    assert not named, f"named colours: {named}"
    assert not functions, f"colour functions: {functions}"


def test_the_depth_rule_flips_between_themes():
    """Dark gets depth from surfaces growing lighter as they come forward;
    light has nowhere lighter to go, so it goes the other way."""
    assert luminance(DARK["--surface-raised"]) > luminance(DARK["--surface"])
    assert luminance(DARK["--surface"]) > luminance(DARK["--surface-sunken"])

    assert luminance(LIGHT["--surface-raised"]) > luminance(LIGHT["--surface"])
    assert luminance(LIGHT["--surface"]) > luminance(LIGHT["--surface-sunken"])


def test_the_themes_are_actually_light_and_dark():
    assert luminance(DARK["--surface"]) < 0.1
    assert luminance(LIGHT["--surface"]) > 0.8


# --- motion -----------------------------------------------------------------

def test_reduced_motion_is_honoured():
    assert "prefers-reduced-motion: reduce" in CSS


def test_reduced_motion_does_not_use_a_zero_duration():
    """0.01ms rather than 0, so transition-end handlers still fire."""
    reduced = CSS[CSS.index("prefers-reduced-motion"):]

    assert "0.01ms" in reduced
    assert not re.search(r"transition-duration:\s*0s", reduced)
