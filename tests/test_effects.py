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
