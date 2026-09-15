"""The window's own size, which is the one thing main.py decides by itself.

Not how it looks -- that is `test_theme.py` and the design system. This is the
arithmetic, and the arithmetic had a real bug in it: `create_window` takes
logical pixels and `webview.screens` reports physical ones, so on any display
with scaling the two were being compared directly and the window came out
taller than the screen.
"""

from __future__ import annotations

import pytest

import main


class FakeScreen:
    def __init__(self, width, height):
        self.width = width
        self.height = height


@pytest.fixture
def display(monkeypatch):
    """Pretend the machine has one screen, of a given size and scaling.

    The size is in physical pixels, the way webview reports it.
    """

    def use(width, height, scale=1.0):
        monkeypatch.setattr(main.webview, "screens", [FakeScreen(width, height)])
        monkeypatch.setattr(main, "display_scale", lambda: scale)

    return use


def test_a_big_screen_gets_the_size_the_page_wants(display):
    display(2560, 1440)

    assert main.window_size() == main.WANTED_SIZE


def test_a_laptop_screen_gets_a_window_that_fits_on_it(display):
    """1366x768 is still a common machine, and the wanted size does not fit."""
    display(1366, 768)

    width, height = main.window_size()

    assert width <= 1366 - main.SCREEN_MARGIN[0]
    assert height <= 768 - main.SCREEN_MARGIN[1]


def test_display_scaling_is_taken_off_the_screen_size(display):
    """The bug this file exists for.

    A 1920x1080 screen at 125% is 1536x864 in the units create_window uses. A
    window asked for in those units has to be compared against those, or
    Windows clamps it and the page opens shorter than it needs and scrolls.
    """
    display(1920, 1080, scale=1.25)

    _, height = main.window_size()

    assert height <= 864 - main.SCREEN_MARGIN[1]


def test_the_same_screen_unscaled_allows_a_taller_window(display):
    """The same pixels, no scaling: more room, and it should be used."""
    display(1920, 1080, scale=1.0)
    unscaled = main.window_size()[1]

    display(1920, 1080, scale=1.25)
    scaled = main.window_size()[1]

    assert unscaled > scaled


def test_the_bottom_of_the_window_clears_the_taskbar(display):
    """The Convert button is at the bottom; behind the taskbar it is unusable."""
    display(1920, 1080, scale=1.25)

    _, height = main.window_size()

    assert height + main.SCREEN_MARGIN[1] <= 1080 / 1.25


def test_a_tiny_screen_still_gets_a_usable_window(display):
    """Never below the minimum: smaller than that is a layout collapsed into
    squeezed panels, and overflowing a very small screen beats drawing
    something unusable on it."""
    display(800, 600)

    width, height = main.window_size()

    assert (width, height) >= main.MIN_SIZE
    assert width <= max(main.MIN_SIZE[0], 800 - main.SCREEN_MARGIN[0])


def test_the_minimum_wins_over_a_screen_too_small_for_it(display):
    display(600, 400)

    assert main.window_size() == main.MIN_SIZE


def test_no_screen_to_ask_is_not_a_reason_to_fail(monkeypatch):
    """webview.screens can raise before the GUI is up. Opening anyway beats
    not opening at all."""

    class Exploding:
        def __getitem__(self, index):
            raise RuntimeError("no display")

    monkeypatch.setattr(main.webview, "screens", Exploding())

    assert main.window_size() == main.WANTED_SIZE


def test_the_scale_is_never_zero_or_negative():
    """It is a divisor. A nonsense value would be worse than no scaling."""
    assert main.display_scale() > 0


def test_the_wanted_size_is_wide_rather_than_tall():
    """Past 62rem the layout goes two-column, which is what turns spare width
    into log height -- and height is the scarce one on a scaled 1080p screen."""
    width, height = main.WANTED_SIZE

    assert width > height
    assert width >= 62 * 16, "narrower than the two-column breakpoint"


def test_the_wanted_height_fits_a_scaled_1080p_screen(display):
    """The machine this was reported on. Asking for more is asking Windows to
    clamp it, which is how the page came to scroll."""
    display(1920, 1080, scale=1.25)

    assert main.window_size() == (main.WANTED_SIZE[0], 864 - main.SCREEN_MARGIN[1])


def test_the_minimum_is_smaller_than_the_default():
    assert main.MIN_SIZE[0] < main.WANTED_SIZE[0]
    assert main.MIN_SIZE[1] < main.WANTED_SIZE[1]
