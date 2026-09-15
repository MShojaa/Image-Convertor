"""The window's own size, which is the one thing main.py decides by itself.

Not how it looks -- that is `test_theme.py` and the design system. This is the
arithmetic: big enough for the page, never bigger than the screen it has to
open on.
"""

from __future__ import annotations

import sys
import types

import pytest

import main


class FakeScreen:
    def __init__(self, width, height):
        self.width = width
        self.height = height


@pytest.fixture
def screen(monkeypatch):
    """Pretend the machine has one screen of a given size."""

    def use(width, height):
        monkeypatch.setattr(main.webview, "screens", [FakeScreen(width, height)])

    return use


def test_a_big_screen_gets_the_size_the_page_wants(screen):
    screen(2560, 1440)

    assert main.window_size() == main.WANTED_SIZE


def test_a_laptop_screen_gets_a_window_that_fits_on_it(screen):
    """1366x768 is still a common machine, and the wanted height does not fit."""
    screen(1366, 768)

    width, height = main.window_size()

    assert width <= 1366 - main.SCREEN_MARGIN[0]
    assert height <= 768 - main.SCREEN_MARGIN[1]


def test_the_bottom_of_the_window_clears_the_taskbar(screen):
    """The Convert button is at the bottom; behind the taskbar it is unusable."""
    screen(1920, 1080)

    _, height = main.window_size()

    assert height <= 1080 - main.SCREEN_MARGIN[1]


def test_a_tiny_screen_still_gets_a_usable_window(screen):
    """Smaller than the minimum is a layout collapsed into squeezed panels.
    Better to overflow a very small screen than to draw something unusable."""
    screen(800, 600)

    assert main.window_size() == main.MIN_SIZE


def test_no_screen_to_ask_is_not_a_reason_to_fail(monkeypatch):
    """webview.screens can raise before the GUI is up. Opening anyway beats
    not opening at all."""

    class Exploding:
        def __getitem__(self, index):
            raise RuntimeError("no display")

    monkeypatch.setattr(main.webview, "screens", Exploding())

    assert main.window_size() == main.WANTED_SIZE


def test_the_wanted_size_actually_fits_the_page():
    """The page measured 780px of content with the log at its 6rem minimum,
    and the log deserves more than its minimum. Guard the number so it is not
    quietly trimmed later."""
    _, height = main.WANTED_SIZE

    assert height >= 780 + 140, "the page would open with a scrollbar again"


def test_the_minimum_is_smaller_than_the_default():
    assert main.MIN_SIZE[0] < main.WANTED_SIZE[0]
    assert main.MIN_SIZE[1] < main.WANTED_SIZE[1]
