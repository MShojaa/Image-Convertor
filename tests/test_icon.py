"""The icon: that it exists, that it is the right shape, and that it survives.

Not whether it looks good -- that is a matter for eyes. These are the things
that break silently: a missing size in the .ico (Windows scales the nearest
one and it goes soft), a logo that stopped being square, or a regenerated
icon that came out blank.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICON = ROOT / "assets" / "icon.ico"
LOGO = ROOT / "UI" / "logo.png"
PNG = ROOT / "assets" / "icon.png"

# What Windows reaches for: 16 and 32 for the taskbar and title bar, 48 in
# Explorer, 256 for the large view.
NEEDED_SIZES = {16, 24, 32, 48, 64, 128, 256}


def test_the_icon_is_committed():
    """The build passes it to PyInstaller; a clone without it builds a
    default-icon exe and nothing says why."""
    assert ICON.is_file()


def test_the_icon_carries_every_size_windows_asks_for():
    with Image.open(ICON) as icon:
        assert {size[0] for size in icon.info["sizes"]} >= NEEDED_SIZES


@pytest.mark.parametrize("size", sorted(NEEDED_SIZES))
def test_each_size_is_really_in_there(size):
    """A size listed but not stored comes back as the nearest one, scaled."""
    with Image.open(ICON) as icon:
        icon.size = (size, size)
        icon.load()
        assert icon.size == (size, size)


@pytest.mark.parametrize("size", sorted(NEEDED_SIZES))
def test_no_size_came_out_blank(size):
    """A drawing bug at one size is invisible until someone sees that size."""
    with Image.open(ICON) as icon:
        icon.size = (size, size)
        icon.load()
        pixels = icon.convert("RGBA")

    levels = {value for value in pixels.convert("L").tobytes()}
    assert len(levels) > 3, f"the {size}px icon is nearly flat"


@pytest.mark.parametrize("size", sorted(NEEDED_SIZES))
def test_the_corners_are_transparent(size):
    """It is a rounded tile. Square corners mean the mask was lost."""
    with Image.open(ICON) as icon:
        icon.size = (size, size)
        icon.load()
        alpha = icon.convert("RGBA").getchannel("A")

    assert alpha.getpixel((0, 0)) < 128, "the top-left corner is not transparent"


def test_the_icon_says_what_the_app_does():
    """Both halves are used: a light photo side and a hard black-and-white
    side. If the dither stopped being applied the right half would go smooth,
    and this is the cheapest way to notice."""
    with Image.open(PNG) as png:
        grey = png.convert("L")

    width, height = grey.size
    left = grey.crop((width // 4, 0, width // 2, height))
    right = grey.crop((width // 2, 0, width * 3 // 4, height))

    # A dither has only two levels in it; a photo has many.
    assert len(set(right.tobytes())) < len(set(left.tobytes()))


def test_the_logo_is_square_and_big_enough_for_a_high_dpi_display():
    """It is drawn at 28px and has to stay sharp at 200%."""
    with Image.open(LOGO) as logo:
        assert logo.width == logo.height
        assert logo.width >= 56


def test_the_logo_has_transparency():
    """It sits on both themes' backgrounds, so its corners must not be opaque."""
    with Image.open(LOGO) as logo:
        assert logo.mode == "RGBA"
        assert logo.getchannel("A").getpixel((0, 0)) < 128
