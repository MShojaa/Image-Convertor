"""The effect values themselves: parsing them, ordering them, applying them.

What each effect does to pixels is checked in `test_converter.py`, next to the
rest of the conversion. This file is about the machinery around them -- the
part that has to keep working as effects are added.
"""

from __future__ import annotations

import pytest
from PIL import Image

from image_convertor.effects import (
    DEFAULT_THRESHOLD,
    REGISTRY,
    Blur,
    Effect,
    Monochrome,
    apply_effects,
    describe,
    order_effects,
    parse_effect,
)


# --- parsing -------------------------------------------------------------

def test_a_bare_name_takes_the_default():
    assert parse_effect("monochrome") == Monochrome(None)


def test_an_argument_is_the_effects_one_setting():
    assert parse_effect("monochrome:200") == Monochrome(200)


@pytest.mark.parametrize("text", ["MONOCHROME", "  monochrome  ", "Monochrome:200 "])
def test_parsing_is_forgiving_about_case_and_space(text):
    assert isinstance(parse_effect(text), Monochrome)


def test_an_unknown_effect_names_the_known_ones():
    """The error has to be the help, because there is nowhere else to look."""
    with pytest.raises(ValueError) as raised:
        parse_effect("sepia")

    message = str(raised.value)
    assert "sepia" in message
    for name in REGISTRY:
        assert name in message


@pytest.mark.parametrize("text", ["", "   ", "monochrome:", "monochrome:dark"])
def test_parsing_rejects_nonsense(text):
    if text.strip().endswith(":"):
        # A trailing colon is an empty argument, which means "take the default"
        assert parse_effect(text) == Monochrome(None)
        return
    with pytest.raises(ValueError):
        parse_effect(text)


def test_a_threshold_outside_the_grey_range_is_refused():
    """Checked by the value, not by the caller, so every way in gets it."""
    for bad in (-1, 256):
        with pytest.raises(ValueError):
            Monochrome(bad)


# --- ordering ------------------------------------------------------------

def test_effects_run_in_their_own_order_not_the_given_one():
    """Monochrome runs last whatever position it was named in."""
    given = (Monochrome(128),)
    assert order_effects(given) == given


def test_one_of_each_kind_survives_and_it_is_the_last():
    """A front end that lets someone change their mind appends; it does not edit."""
    ordered = order_effects((Monochrome(None), Monochrome(200)))

    assert ordered == (Monochrome(200),)


def test_ordering_nothing_gives_nothing():
    assert order_effects(()) == ()


def test_order_is_a_property_of_the_kind_not_the_instance():
    """Two of the same effect cannot disagree about when they run."""
    assert Monochrome(None).order == Monochrome(200).order


def test_every_registered_effect_has_a_name_and_a_place():
    """Adding an effect to the registry without these is the easy mistake."""
    for name, kind in REGISTRY.items():
        assert kind.name == name
        assert kind.order > 0
        assert kind.apply is not Effect.apply  # it actually does something

    orders = [kind.order for kind in REGISTRY.values()]
    assert len(set(orders)) == len(orders), "two effects claim the same place"


def test_monochrome_runs_last_of_everything():
    """Everything else works on grey levels monochrome throws away."""
    assert Monochrome.order == max(kind.order for kind in REGISTRY.values())


# --- applying ------------------------------------------------------------

def test_applying_nothing_leaves_the_image_alone():
    image = Image.new("RGB", (4, 4), (123, 45, 67))

    result = apply_effects(image, ())

    assert result.mode == "RGB"
    assert result.getpixel((0, 0)) == (123, 45, 67)


def test_applying_monochrome_gives_one_bit():
    result = apply_effects(Image.new("RGB", (4, 4), (10, 10, 10)), (Monochrome(128),))

    assert result.mode == "1"


def test_a_repeated_effect_is_applied_once_with_the_last_value():
    grey = Image.new("RGB", (4, 4), (160, 160, 160))

    # 200 cuts above 160 so the result is black; 100 would leave it white.
    result = apply_effects(grey, (Monochrome(100), Monochrome(200)))

    assert result.convert("L").getpixel((0, 0)) == 0


# --- describing ----------------------------------------------------------

def test_describe_says_what_will_run():
    assert describe((Monochrome(None),)) == "monochrome"
    assert describe((Monochrome(200),)) == "monochrome:200"


def test_describe_says_so_when_there_is_nothing():
    """"no effects" is a real answer and has to read like one."""
    assert describe(()) == "no effects"


def test_what_describe_prints_can_be_parsed_back():
    """The line the app prints is a line that could have been typed."""
    for effect in (Monochrome(None), Monochrome(DEFAULT_THRESHOLD)):
        assert parse_effect(effect.described()) == effect


# --- blur ----------------------------------------------------------------

def edge_image():
    """Half black, half white, with one hard vertical edge down the middle."""
    image = Image.new("RGB", (16, 4), (255, 255, 255))
    for x in range(8):
        for y in range(4):
            image.putpixel((x, y), (0, 0, 0))
    return image


def greys(image):
    """The middle row, as grey levels."""
    row = image.convert("L")
    return [row.getpixel((x, 2)) for x in range(row.width)]


def test_blur_softens_an_edge():
    """The point of it: pixels that were 0 or 255 land in between."""
    before = greys(edge_image())
    after = greys(Blur(2).apply(edge_image()))

    assert set(before) == {0, 255}
    assert any(0 < value < 255 for value in after)


def test_a_bigger_radius_spreads_further():
    narrow = greys(Blur(1).apply(edge_image()))
    wide = greys(Blur(4).apply(edge_image()))

    def softened(row):
        return sum(1 for value in row if 0 < value < 255)

    assert softened(wide) > softened(narrow)


def test_a_zero_radius_changes_nothing():
    """Not an error -- it is the identity, and a slider that starts at 0 needs it."""
    assert greys(Blur(0).apply(edge_image())) == greys(edge_image())


def test_a_negative_radius_is_refused():
    with pytest.raises(ValueError):
        Blur(-1)


def test_blur_takes_a_fractional_radius():
    """Below 1 is the useful range on a small image, so it cannot be an int."""
    assert parse_effect("blur:0.5") == Blur(0.5)


def test_blur_runs_before_monochrome():
    """A 1-bit image has nothing between black and white left to smear."""
    assert Blur.order < Monochrome.order

    ordered = order_effects((Monochrome(128), Blur(2)))
    assert ordered == (Blur(2), Monochrome(128))


def test_blur_into_a_hard_cut_moves_the_edge_but_keeps_two_levels():
    """The pairing worth knowing about: a soft-edged threshold, still 1-bit."""
    result = apply_effects(edge_image(), (Blur(3), Monochrome(128)))

    assert result.mode == "1"
    assert set(greys(result)) == {0, 255}


def test_a_blur_radius_reads_back_without_a_trailing_zero():
    """describe() is meant to be re-typable; "blur:2.0" is noise."""
    assert Blur(2).described() == "blur:2"
    assert Blur(0.5).described() == "blur:0.5"
    assert parse_effect(Blur(2).described()) == Blur(2)


def test_a_blur_radius_that_is_not_a_number_is_refused():
    with pytest.raises(ValueError) as raised:
        parse_effect("blur:lots")

    assert "blur radius" in str(raised.value)
