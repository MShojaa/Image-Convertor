"""The effect values themselves: parsing them, ordering them, applying them.

What each effect does to pixels is checked in `test_converter.py`, next to the
rest of the conversion. This file is about the machinery around them -- the
part that has to keep working as effects are added.
"""

from __future__ import annotations

import pytest
from PIL import Image

from image_convertor.effects import (
    DEFAULT_NOISE_AMOUNT,
    DEFAULT_THRESHOLD,
    DEFAULT_KEY_COLOUR,
    NEUTRAL_TINT,
    REGISTRY,
    SETTINGS,
    Blur,
    Effect,
    Grayscale,
    Monochrome,
    Noise,
    Transparent,
    apply_effects,
    describe,
    order_effects,
    parse_effect,
    restore_clear,
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


# --- noise ---------------------------------------------------------------

def flat_grey(value=128, size=(12, 12)):
    """A flat grey. RGB rather than L, because that is what the pipeline hands
    an effect, and grey RGB keeps the old assertions about levels meaningful."""
    return Image.new("RGB", size, (value, value, value))


def levels(image):
    """Every pixel as a grey level.

    Through tobytes() rather than getdata(), which Pillow has deprecated: an
    "L" image is one byte per pixel, so the bytes are the levels.
    """
    return list(image.convert("L").tobytes())


def test_noise_moves_pixels_off_a_flat_grey():
    before = flat_grey()
    after = Noise(40).apply(before)

    assert set(levels(before)) == {128}
    assert len(set(levels(after))) > 1


def test_the_same_seed_gives_the_same_noise():
    """Converting the same folder twice has to give the same files."""
    once = Noise(40, seed=7).apply(flat_grey())
    twice = Noise(40, seed=7).apply(flat_grey())

    assert levels(once) == levels(twice)


def test_a_different_seed_gives_different_noise():
    assert levels(Noise(40, seed=1).apply(flat_grey())) != levels(
        Noise(40, seed=2).apply(flat_grey())
    )


def test_the_default_seed_is_fixed_not_the_clock():
    """The whole reason the seed exists: no seed must still be reproducible."""
    assert levels(Noise(40).apply(flat_grey())) == levels(Noise(40).apply(flat_grey()))


def test_the_amount_bounds_how_far_a_pixel_moves():
    values = set(levels(Noise(10, seed=3).apply(flat_grey(128))))

    assert values, "no pixels came back"
    assert min(values) >= 118 and max(values) <= 138


def test_noise_does_not_wrap_at_the_ends():
    """255 + noise must clamp to white, not roll round to black."""
    light = set(levels(Noise(60, seed=1).apply(flat_grey(250))))
    dark = set(levels(Noise(60, seed=1).apply(flat_grey(5))))

    assert max(light) == 255 and min(light) > 150
    assert min(dark) == 0 and max(dark) < 105


def test_a_zero_amount_changes_nothing():
    assert levels(Noise(0).apply(flat_grey())) == [128] * 144


@pytest.mark.parametrize("amount", [-1, 256])
def test_an_amount_outside_the_grey_range_is_refused(amount):
    with pytest.raises(ValueError):
        Noise(amount)


def test_noise_runs_after_blur_and_before_monochrome():
    """Blur over noise is a quieter noise, which is not what either flag says."""
    assert Blur.order < Noise.order < Monochrome.order

    assert order_effects((Monochrome(128), Noise(20), Blur(1))) == (
        Blur(1),
        Noise(20),
        Monochrome(128),
    )


def test_noise_keeps_a_colour_image_in_colour():
    """It used to convert to grey first, which was only defensible while
    monochrome always came next. It no longer does."""
    assert Noise(20).apply(Image.new("RGB", (4, 4), (200, 30, 30))).mode == "RGB"


def test_noise_does_not_change_the_colour_it_lands_on():
    """The same noise on every channel moves a pixel lighter or darker.
    A separate roll per channel would move R away from G, which is a change
    of hue: a grey wall comes back speckled pink and green."""
    noised = Noise(30, seed=3).apply(Image.new("RGB", (16, 16), (200, 60, 60)))

    pixels = noised.convert("RGB")
    raw = pixels.tobytes()
    gaps = {
        (raw[i] - raw[i + 1], raw[i + 1] - raw[i + 2]) for i in range(0, len(raw), 3)
    }
    assert gaps == {(140, 0)}, "the channels moved apart from each other"


def test_noise_still_moves_a_colour_image():
    before = Image.new("RGB", (16, 16), (120, 90, 60))
    after = Noise(30, seed=2).apply(before)

    assert len(set(after.convert("L").tobytes())) > 1


def test_noise_leaves_alpha_alone():
    """Noising transparency makes a clean edge fizzle, and nothing about
    "add noise" says the shape should change."""
    noised = Noise(60, seed=1).apply(Image.new("RGBA", (8, 8), (10, 150, 10, 128)))

    assert noised.mode == "RGBA"
    assert set(noised.getchannel("A").tobytes()) == {128}


def test_noise_keeps_a_grey_image_grey():
    assert Noise(20).apply(Image.new("L", (4, 4), 128)).mode == "L"


def test_noise_on_a_one_bit_image_gives_it_levels_to_move_in():
    """Two levels plus noise is two levels again; staying 1-bit would do
    nothing at all."""
    result = Noise(40, seed=1).apply(Image.new("1", (16, 16), 1))

    assert result.mode == "L"
    assert len(set(result.tobytes())) > 1


def test_noise_on_a_palette_image_works():
    palette = Image.new("P", (8, 8), 3)
    palette.putpalette([0, 0, 0] * 200 + [90, 120, 200] * 56)

    assert Noise(20).apply(palette).mode in ("RGB", "RGBA")


def test_noise_into_a_hard_cut_is_a_coarse_dither():
    """A flat grey plus noise, cut at the middle, comes out as scattered dots."""
    result = apply_effects(flat_grey(128), (Noise(60, seed=4), Monochrome(128)))
    values = set(levels(result))

    assert result.mode == "1"
    assert values == {0, 255}, "a hard cut leaves two levels"


# --- the settings after the name -----------------------------------------

def test_a_second_setting_is_read_in_order():
    assert parse_effect("noise:40:7") == Noise(40, 7)


def test_an_omitted_setting_takes_its_default():
    """"noise::7" is the default amount with a chosen seed, not an error."""
    assert parse_effect("noise::7") == Noise(DEFAULT_NOISE_AMOUNT, 7)


def test_too_many_settings_says_what_the_effect_takes():
    with pytest.raises(ValueError) as raised:
        parse_effect("noise:1:2:3:4")

    assert "amount, seed, keep_clear" in str(raised.value)


def test_the_default_seed_is_left_out_of_the_description():
    """describe() is re-typable, and a seed nobody chose is noise in the line."""
    assert Noise(40).described() == "noise:40"
    assert Noise(40, 7).described() == "noise:40:7"
    assert parse_effect(Noise(40, 7).described()) == Noise(40, 7)


# --- grayscale -----------------------------------------------------------

def test_grayscale_takes_the_colour_out():
    result = Grayscale().apply(Image.new("RGB", (4, 4), (200, 60, 60)))

    assert result.mode == "L"


def test_the_default_tint_is_plain_grayscale():
    """Mid grey maps black to black, white to white and grey to itself, so the
    default needs no special case to mean "no tint"."""
    assert Grayscale().tint == NEUTRAL_TINT
    assert Grayscale().described() == "grayscale"


def test_the_default_tint_matches_a_straight_conversion():
    colourful = Image.new("RGB", (8, 8), (200, 60, 90))

    assert levels(Grayscale().apply(colourful)) == levels(colourful.convert("L"))


def test_a_tint_puts_one_colour_back():
    result = Grayscale((138, 90, 43)).apply(Image.new("RGB", (4, 4), (128, 128, 128)))

    assert result.mode == "RGB"
    red, green, blue = result.getpixel((0, 0))
    assert red > green > blue, "a warm tint should come out warm"


def test_a_tint_keeps_the_ends_of_the_range():
    """It is a duotone -- black stays black and white stays white -- not a
    wash, which would drag the highlights down with everything else."""
    ramp = Image.new("L", (3, 1))
    ramp.putpixel((0, 0), 0)
    ramp.putpixel((1, 0), 128)
    ramp.putpixel((2, 0), 255)

    toned = Grayscale((138, 90, 43)).apply(ramp.convert("RGB"))

    assert toned.getpixel((0, 0)) == (0, 0, 0)
    assert toned.getpixel((2, 0)) == (255, 255, 255)


def test_a_tint_keeps_the_shading():
    """The point of a duotone: every level of the original is still distinct."""
    ramp = Image.new("L", (32, 1))
    for x in range(32):
        ramp.putpixel((x, 0), x * 8)

    toned = Grayscale((138, 90, 43)).apply(ramp.convert("RGB"))

    assert len(set(levels(toned))) > 20


def test_grayscale_keeps_alpha():
    clear = Image.new("RGBA", (4, 4), (200, 60, 60, 77))

    plain = Grayscale().apply(clear)
    tinted = Grayscale((138, 90, 43)).apply(clear)

    assert plain.mode == "LA"
    assert tinted.mode == "RGBA"
    for result in (plain, tinted):
        assert set(result.getchannel("A").tobytes()) == {77}


def test_grayscale_runs_after_noise_and_before_monochrome():
    assert Noise.order < Grayscale.order < Monochrome.order

    assert order_effects((Monochrome(128), Grayscale(), Blur(1), Noise(10))) == (
        Blur(1),
        Noise(10),
        Grayscale(),
        Monochrome(128),
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("grayscale", NEUTRAL_TINT),
        ("grayscale:gray", NEUTRAL_TINT),
        ("grayscale:#8a5a2b", (138, 90, 43)),
        ("grayscale:red", (255, 0, 0)),
    ],
)
def test_a_tint_can_be_named_or_written_in_hex(text, expected):
    assert parse_effect(text).tint == expected


def test_a_tint_that_is_not_a_colour_says_so():
    with pytest.raises(ValueError) as raised:
        parse_effect("grayscale:ultraviolet")

    assert "colour" in str(raised.value)


def test_a_tint_reads_back_as_hex():
    """describe() has to be re-typable, and a name is not always available."""
    effect = Grayscale((138, 90, 43))

    assert parse_effect(effect.described()) == effect


def test_a_tint_out_of_range_is_refused():
    for bad in ((-1, 0, 0), (0, 256, 0)):
        with pytest.raises(ValueError):
            Grayscale(bad)


def test_grayscale_into_monochrome_still_gives_two_levels():
    toned = apply_effects(
        Image.new("RGB", (16, 16), (200, 60, 60)),
        (Grayscale((138, 90, 43)), Monochrome(128)),
    )

    assert toned.mode == "1"


# --- transparent ---------------------------------------------------------

def half_white(size=(8, 4)):
    """Left half white, right half red."""
    image = Image.new("RGB", size, (255, 255, 255))
    for x in range(size[0] // 2, size[0]):
        for y in range(size[1]):
            image.putpixel((x, y), (200, 30, 30))
    return image


def alpha_of(image):
    return list(image.getchannel("A").tobytes())


def test_transparent_keys_out_the_colour_and_keeps_the_rest():
    result = Transparent().apply(half_white())

    assert result.mode == "RGBA"
    row = alpha_of(result)[:8]
    assert row == [0, 0, 0, 0, 255, 255, 255, 255]


def test_white_is_the_default_colour():
    """A scanned page, a logo on a card and an exported diagram all have it."""
    assert Transparent().colour == DEFAULT_KEY_COLOUR == (255, 255, 255)


def test_another_colour_can_be_keyed():
    result = Transparent(colour=(200, 30, 30)).apply(half_white())

    row = alpha_of(result)[:8]
    assert row == [255, 255, 255, 255, 0, 0, 0, 0]


def test_exact_leaves_a_nearly_white_pixel_alone():
    """A jpg's white background wanders a few levels; exact is for flat PNGs."""
    near = Image.new("RGB", (4, 1), (252, 254, 253))

    assert set(alpha_of(Transparent(match="exact").apply(near))) == {255}


def test_a_tolerance_catches_a_nearly_white_pixel():
    near = Image.new("RGB", (4, 1), (252, 254, 253))

    assert set(alpha_of(Transparent(match="tolerance").apply(near))) == {0}


def test_exact_is_a_tolerance_of_zero():
    """Kept as its own named choice rather than asking people to work it out."""
    near = Image.new("RGB", (4, 1), (252, 254, 253))

    assert alpha_of(Transparent(match="exact").apply(near)) == alpha_of(
        Transparent(match="tolerance", tolerance=0).apply(near)
    )


def test_the_tolerance_is_the_worst_channel_not_the_average():
    """"Within 12 of white" has to mean all three channels are; an average
    would let a strong blue through on the strength of its red."""
    blueish = Image.new("RGB", (4, 1), (255, 255, 200))

    assert set(alpha_of(Transparent(tolerance=12).apply(blueish))) == {255}


def test_a_wider_tolerance_catches_more():
    grey = Image.new("RGB", (4, 1), (200, 200, 200))

    assert set(alpha_of(Transparent(tolerance=12).apply(grey))) == {255}
    assert set(alpha_of(Transparent(tolerance=60).apply(grey))) == {0}


def test_soft_edges_give_partial_alpha_at_the_boundary():
    """A hard key on an antialiased edge leaves a staircase."""
    hard = alpha_of(Transparent(soft=False).apply(half_white((16, 4))))
    soft = alpha_of(Transparent(soft=True).apply(half_white((16, 4))))

    assert set(hard) == {0, 255}
    assert any(0 < value < 255 for value in soft), "the edge stayed hard"


def test_soft_edges_work_with_an_exact_match_too():
    """It feathers the mask, not the match, so it is available to both."""
    soft = alpha_of(Transparent(match="exact", soft=True).apply(half_white((16, 4))))

    assert any(0 < value < 255 for value in soft)


def test_an_already_transparent_pixel_stays_transparent():
    """The mask is combined with the alpha it arrived with, not swapped for it,
    so running this twice does not undo the first one."""
    clear = Image.new("RGBA", (4, 4), (200, 30, 30, 0))

    assert set(alpha_of(Transparent().apply(clear))) == {0}


def test_transparent_runs_before_everything_else():
    """Keying after a blur would be keying the blur's own soft edges."""
    assert Transparent.order < min(
        kind.order for kind in REGISTRY.values() if kind is not Transparent
    )


def test_transparent_reads_back_as_it_would_be_typed():
    effect = Transparent(colour=(0, 0, 0), match="exact", tolerance=30, soft=True)

    assert parse_effect(effect.described()) == effect


def test_an_omitted_setting_takes_its_default():
    assert parse_effect("transparent::exact::yes") == Transparent(
        match="exact", soft=True
    )


@pytest.mark.parametrize("word", ["yes", "true", "on", "1"])
def test_a_flag_can_be_said_any_of_the_usual_ways(word):
    assert parse_effect(f"transparent::::{word}").soft is True


@pytest.mark.parametrize("word", ["no", "false", "off", "0"])
def test_a_flag_can_be_denied_any_of_the_usual_ways(word):
    assert parse_effect(f"transparent::::{word}").soft is False


def test_a_flag_that_is_not_yes_or_no_says_so():
    with pytest.raises(ValueError) as raised:
        parse_effect("transparent::::maybe")

    assert "yes or no" in str(raised.value)


def test_an_unknown_match_names_the_ones_there_are():
    with pytest.raises(ValueError) as raised:
        parse_effect("transparent:white:fuzzy")

    assert "tolerance" in str(raised.value) and "exact" in str(raised.value)


def test_a_tolerance_out_of_range_is_refused():
    for bad in (-1, 256):
        with pytest.raises(ValueError):
            Transparent(tolerance=bad)


# --- what the settings say about themselves ------------------------------

def test_every_setting_declares_a_kind_the_window_can_draw():
    drawable = {"number", "colour", "choice", "flag"}

    for settings in SETTINGS.values():
        for setting in settings:
            assert setting.kind in drawable, f"{setting.label} is a {setting.kind}"


def test_a_choice_setting_lists_its_options():
    for settings in SETTINGS.values():
        for setting in settings:
            if setting.kind == "choice":
                assert setting.options, f"{setting.label} offers nothing to choose"
            else:
                assert not setting.options


def test_every_effect_has_a_settings_row():
    """Parsing looks the effect up here; a missing row is a KeyError at use."""
    for kind in REGISTRY.values():
        assert kind in SETTINGS


def test_a_settings_label_matches_a_real_field():
    import dataclasses

    for kind, settings in SETTINGS.items():
        fields = {field.name for field in dataclasses.fields(kind)}
        for setting in settings:
            assert setting.label in fields, f"{kind.name} has no {setting.label}"


# --- leaving the transparent area alone ----------------------------------

def cutout(size=(16, 8)):
    """A hard-edged shape on a clear background: left clear, right opaque."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for x in range(size[0] // 2, size[0]):
        for y in range(size[1]):
            image.putpixel((x, y), (200, 60, 60, 255))
    return image


def test_keeping_the_clear_areas_clear_is_the_default():
    """Noise appearing where the user said transparent is a surprise."""
    for kind in (Blur, Noise, Grayscale):
        assert kind().keep_clear is True


def test_monochrome_answers_the_same_question_its_own_way():
    """It cannot have the flag as well: filling the clear areas and then
    putting the original alpha back over the top undoes the fill."""
    assert not hasattr(Monochrome(), "keep_clear")
    assert Monochrome().clear == "white"


def test_the_transparent_effect_has_no_such_flag():
    """It is the one that makes things clear; it cannot be told to leave them."""
    assert not hasattr(Transparent(), "keep_clear")


def test_a_blur_does_not_soften_the_silhouette_by_default():
    blurred = Blur(3).apply(cutout())
    kept = apply_effects(cutout(), (Blur(3),))

    assert any(0 < v < 255 for v in blurred.getchannel("A").tobytes())
    assert set(kept.getchannel("A").tobytes()) == {0, 255}, "the cut-out edge moved"


def test_turning_it_off_lets_the_blur_reach_the_alpha():
    """For when the whole rectangle really is the picture."""
    softened = apply_effects(cutout(), (Blur(3, keep_clear=False),))

    assert any(0 < v < 255 for v in softened.getchannel("A").tobytes())


def test_noise_does_not_reach_into_the_clear_area():
    noised = apply_effects(cutout(), (Noise(60, seed=1),))
    left_half = noised.crop((0, 0, 8, 8))

    assert set(left_half.getchannel("A").tobytes()) == {0}
    assert set(left_half.convert("RGB").tobytes()) == {0}, "colour changed under the clear"


def test_the_visible_part_is_still_affected():
    noised = apply_effects(cutout(), (Noise(60, seed=1),))
    right_half = noised.crop((8, 0, 16, 8)).convert("RGB")

    assert len(set(right_half.tobytes())) > 1


def test_grayscale_leaves_the_clear_area_alone():
    toned = apply_effects(cutout(), (Grayscale((138, 90, 43)),))

    assert set(toned.crop((0, 0, 8, 8)).getchannel("A").tobytes()) == {0}


def test_monochrome_gives_one_bit_by_default():
    """One bit or a transparent area, not both -- and the bit wins."""
    result = apply_effects(cutout(), (Monochrome(128),))

    assert result.mode == "1"


def test_monochrome_fills_the_clear_area_with_white_not_black():
    """A transparent pixel keeps whatever colour hid under it, which in a PNG
    is usually black -- so a logo's clear background would dither into a black
    rectangle."""
    result = apply_effects(cutout(), (Monochrome(128),))

    assert set(result.convert("L").crop((0, 0, 8, 8)).tobytes()) == {255}


def test_monochrome_can_keep_the_alpha_instead():
    result = apply_effects(cutout(), (Monochrome(128, clear="keep"),))

    assert result.mode == "LA"
    assert set(result.crop((0, 0, 8, 8)).getchannel("A").tobytes()) == {0}


def test_an_unknown_clear_choice_names_the_ones_there_are():
    with pytest.raises(ValueError) as raised:
        Monochrome(clear="invisible")

    assert "white" in str(raised.value) and "keep" in str(raised.value)


def test_the_clear_choice_reads_back_as_it_would_be_typed():
    effect = Monochrome(128, clear="keep")

    assert parse_effect(effect.described()) == effect


def test_an_opaque_image_is_unaffected_by_the_flag():
    """Nothing to protect, so it must not change what happens."""
    opaque = Image.new("RGB", (16, 8), (200, 60, 60))

    protected = apply_effects(opaque, (Noise(40, seed=2),))
    unprotected = apply_effects(opaque, (Noise(40, seed=2, keep_clear=False),))

    assert levels(protected) == levels(unprotected)


def test_a_half_transparent_pixel_gets_half_the_effect():
    """It falls out of using the alpha as the mask, and it is the right answer:
    an antialiased edge does not end up with a hard line of untouched pixels."""
    # Mid grey, not black: a duotone maps black to black, so a black pixel
    # would show nothing whether the effect reached it or not.
    half = Image.new("RGBA", (4, 4), (128, 128, 128, 128))

    result = apply_effects(half, (Grayscale((255, 0, 0)),))
    red, green, blue = result.convert("RGB").getpixel((0, 0))

    assert red > blue, "the effect did not reach a half-visible pixel"
    assert red < 255, "a half-visible pixel got the whole effect"
    assert result.getchannel("A").getpixel((0, 0)) == 128


def test_restore_clear_does_nothing_to_an_image_without_alpha():
    before = Image.new("RGB", (4, 4), (10, 20, 30))
    after = Image.new("RGB", (4, 4), (40, 50, 60))

    assert restore_clear(before, after) is after


def test_the_flag_reads_back_as_it_would_be_typed():
    for effect in (Blur(2, keep_clear=False), Noise(40, 7, keep_clear=False)):
        assert parse_effect(effect.described()) == effect
