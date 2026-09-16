"""The conversion rules, checked one at a time on images built in memory."""

from __future__ import annotations

import pytest
from PIL import Image

from image_convertor.converter import (
    Converted,
    Size,
    convert_image,
    find_images,
    fit_into_box,
    flatten_to_white,
    parse_size,
)
from image_convertor.effects import DEFAULT_THRESHOLD, Monochrome


def to_monochrome(image, threshold):
    """The monochrome effect, called the way this file has always called it."""
    return Monochrome(threshold).apply(image)

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def rows(image: Image.Image) -> list[str]:
    """A picture of the image, '#' for black, '.' for white, for asserting on."""
    grey = image.convert("L")
    pixels = grey.load()
    return [
        "".join("#" if pixels[x, y] < 128 else "." for x in range(grey.width))
        for y in range(grey.height)
    ]


# --- parse_size ----------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("10x10", Size(10, 10)),
        ("320X240", Size(320, 240)),
        (" 128 x 64 ", Size(128, 64)),
        ("128*64", Size(128, 64)),
        ("128,64", Size(128, 64)),
    ],
)
def test_parse_size_reads_a_box(text, expected):
    assert parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_empty_means_no_resizing(text):
    """Pressing enter is not a bad value, it is a choice -- and it is None."""
    assert parse_size(text) is None


@pytest.mark.parametrize("text", ["100", "axb", "10x", "10x0", "-5x5", "10x-5"])
def test_parse_size_rejects_nonsense(text):
    with pytest.raises(ValueError):
        parse_size(text)


# --- transparency --------------------------------------------------------

def test_transparent_pixels_become_white():
    """The whole point: a clear background must not come out black."""
    image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    assert rows(flatten_to_white(image)) == ["...."] * 4


def test_half_transparent_black_lands_between():
    image = Image.new("RGBA", (1, 1), (0, 0, 0, 128))
    value = flatten_to_white(image).convert("L").getpixel((0, 0))
    assert 100 < value < 155


def test_palette_transparency_becomes_white():
    """A GIF-style palette image keeps its transparency in image.info."""
    image = Image.new("P", (2, 2), 0)
    image.putpalette([0, 0, 0] * 256)
    image.info["transparency"] = 0
    assert rows(flatten_to_white(image)) == [".."] * 2


def test_opaque_image_is_untouched():
    image = Image.new("RGB", (2, 2), BLACK)
    assert rows(flatten_to_white(image)) == ["##"] * 2


# --- fitting into the box ------------------------------------------------

def test_the_specified_case_20x16_into_10x10():
    """From the spec: resize to 10x8 and centre it in a 10x10 white box."""
    fitted = fit_into_box(Image.new("RGB", (20, 16), BLACK), Size(10, 10))

    assert fitted.size == (10, 10)
    assert rows(fitted) == ["." * 10] + ["#" * 10] * 8 + ["." * 10]


def test_a_matching_ratio_leaves_no_white():
    fitted = fit_into_box(Image.new("RGB", (20, 10), BLACK), Size(10, 5))

    assert fitted.size == (10, 5)
    assert rows(fitted) == ["#" * 10] * 5


def test_tall_image_gets_white_at_the_sides():
    fitted = fit_into_box(Image.new("RGB", (10, 20), BLACK), Size(10, 10))

    assert fitted.size == (10, 10)
    assert rows(fitted) == [".." + "#" * 5 + "..."] * 10


def test_small_images_are_centred_not_enlarged():
    """Resizing shrinks. A 4x4 asked for 10x10 stays 4x4, in the middle."""
    fitted = fit_into_box(Image.new("RGB", (4, 4), BLACK), Size(10, 10))

    assert fitted.size == (10, 10)
    assert rows(fitted) == ["." * 10] * 3 + ["..." + "####" + "..."] * 4 + ["." * 10] * 3


def test_the_box_is_never_exceeded():
    for source, box in [((1000, 3), (10, 10)), ((3, 1000), (10, 10)), ((7, 5), (4, 9))]:
        fitted = fit_into_box(Image.new("RGB", source), Size(*box))
        assert fitted.size == box


def test_an_extreme_shrink_keeps_a_pixel():
    """Rounding a 1000x3 down must not produce a zero-height image."""
    fitted = fit_into_box(Image.new("RGB", (1000, 3), BLACK), Size(10, 10))
    assert any("#" in row for row in rows(fitted))


# --- black and white -----------------------------------------------------

def test_hard_cut_keeps_flat_grey_flat():
    """The reason the hard cut exists: dithering speckles a flat fill."""
    grey = Image.new("RGB", (8, 8), (160, 160, 160))

    hard_cut = rows(to_monochrome(grey, DEFAULT_THRESHOLD))
    dithered = rows(to_monochrome(grey, None))

    assert hard_cut == ["." * 8] * 8
    assert "#" in "".join(dithered)


def test_hard_cut_splits_at_the_threshold():
    lighter = Image.new("RGB", (1, 1), (130, 130, 130))
    darker = Image.new("RGB", (1, 1), (126, 126, 126))

    assert rows(to_monochrome(lighter, 128)) == ["."]
    assert rows(to_monochrome(darker, 128)) == ["#"]


def test_output_is_one_bit():
    assert to_monochrome(Image.new("RGB", (2, 2)), None).mode == "1"
    assert to_monochrome(Image.new("RGB", (2, 2)), 128).mode == "1"


# --- the whole thing, on real files --------------------------------------

def test_convert_image_keeps_transparency_through_the_whole_pipeline(tmp_path):
    """A clear PNG used to come out white. It comes out clear."""
    source = tmp_path / "logo.png"
    Image.new("RGBA", (20, 16), (0, 0, 0, 0)).save(source)
    destination = tmp_path / "out" / "logo.png"

    written = convert_image(
        source, destination, Size(10, 10), (Monochrome(DEFAULT_THRESHOLD),)
    )

    assert written.size == Size(10, 10)
    with Image.open(destination) as result:
        assert result.format == "PNG"  # the source's own format, by default
        # "LA", not "1": one bit has no room for a third state.
        assert result.mode == "LA"
        assert set(result.getchannel("A").tobytes()) == {0}


def test_an_opaque_image_still_comes_out_one_bit(tmp_path):
    """Nothing to keep, so nothing is carried: the old shape is unchanged."""
    source = tmp_path / "photo.png"
    Image.new("RGB", (20, 16), (120, 120, 120)).save(source)

    convert_image(source, tmp_path / "out.png", None, (Monochrome(DEFAULT_THRESHOLD),))

    with Image.open(tmp_path / "out.png") as result:
        assert result.mode == "1"


def test_convert_image_without_a_box_keeps_the_size(tmp_path):
    source = tmp_path / "wide.png"
    Image.new("RGB", (20, 16), BLACK).save(source)

    written = convert_image(source, tmp_path / "wide.png", None, (Monochrome(None),))

    assert written.size == Size(20, 16)
    assert not written.shrunk
    assert not written.too_small_to_shrink  # no box asked for, nothing to warn about


def test_convert_image_creates_the_output_folder(tmp_path):
    source = tmp_path / "a.png"
    Image.new("RGB", (2, 2)).save(source)

    convert_image(source, tmp_path / "deep" / "deeper" / "a.png")

    assert (tmp_path / "deep" / "deeper" / "a.png").exists()


# --- finding the input ---------------------------------------------------

def test_find_images_picks_up_images_and_skips_the_rest(tmp_path):
    for name in ("b.png", "a.JPG", "c.bmp", "notes.txt", "data.json"):
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "subfolder").mkdir()

    found = [path.name for path in find_images(tmp_path)]

    assert found == ["a.JPG", "b.png", "c.bmp"]  # sorted, folders left alone


# --- was it actually shrunk? ---------------------------------------------

def convert(source_size, box, tmp_path):
    path = tmp_path / "in.png"
    Image.new("RGB", source_size, BLACK).save(path)
    return convert_image(path, tmp_path / "out.png", box, (Monochrome(None),))


@pytest.mark.parametrize(
    "source, box",
    [
        ((20, 16), (10, 10)),   # shrunk and padded
        ((20, 10), (10, 5)),    # shrunk, same ratio, no padding
        ((20, 4), (10, 10)),    # shrunk on the wide side only
        ((4, 20), (10, 10)),    # shrunk on the tall side only
    ],
)
def test_a_larger_image_reports_a_shrink(source, box, tmp_path):
    result = convert(source, Size(*box), tmp_path)

    assert result.shrunk
    assert not result.too_small_to_shrink


@pytest.mark.parametrize(
    "source, box",
    [
        ((4, 4), (10, 10)),     # smaller both ways
        ((4, 10), (10, 10)),    # already exactly as tall as the box
        ((10, 4), (10, 10)),    # already exactly as wide as the box
    ],
)
def test_an_image_already_inside_the_box_is_reported(source, box, tmp_path):
    result = convert(source, Size(*box), tmp_path)

    assert not result.shrunk
    assert result.too_small_to_shrink
    assert result.size == Size(*box)
    assert result.original == Size(*source)


def test_an_exact_fit_is_not_a_failure_to_shrink(tmp_path):
    """Nothing was shrunk, but nothing was padded either -- no warning."""
    result = convert((10, 10), Size(10, 10), tmp_path)

    assert not result.shrunk
    assert not result.too_small_to_shrink


def test_the_result_is_a_plain_value(tmp_path):
    assert convert((4, 4), Size(10, 10), tmp_path) == Converted(
        size=Size(10, 10), original=Size(4, 4), shrunk=False
    )


# --- transparency through the pipeline -----------------------------------

def test_normalise_keeps_alpha_rather_than_flattening_it():
    """The change this whole version is about: an effect can now see a
    transparent area, because there is still one when it runs."""
    from image_convertor.converter import normalise

    assert normalise(Image.new("RGBA", (4, 4), (0, 0, 0, 0))).mode == "RGBA"
    assert normalise(Image.new("LA", (4, 4), (10, 0))).mode == "RGBA"
    assert normalise(Image.new("RGB", (4, 4))).mode == "RGB"


def test_normalise_keeps_palette_transparency():
    image = Image.new("P", (4, 4), 0)
    image.putpalette([0, 0, 0] * 256)
    image.info["transparency"] = 0

    from image_convertor.converter import normalise

    assert normalise(image).mode == "RGBA"


def test_normalise_leaves_a_palette_without_transparency_opaque():
    image = Image.new("P", (4, 4), 0)
    image.putpalette([10, 20, 30] * 256)

    from image_convertor.converter import normalise

    assert normalise(image).mode == "RGB"


def test_a_transparent_image_is_padded_with_transparency():
    """Padding a logo that asked to keep its clear background with a white
    frame is the one thing it did not ask for."""
    clear = Image.new("RGBA", (20, 16), (0, 0, 0, 255))
    fitted = fit_into_box(clear, Size(10, 10))

    assert fitted.mode == "RGBA"
    assert fitted.getchannel("A").getpixel((0, 0)) == 0      # the padding
    assert fitted.getchannel("A").getpixel((5, 5)) == 255    # the image


def test_an_opaque_image_is_still_padded_with_white():
    fitted = fit_into_box(Image.new("RGB", (20, 16), (0, 0, 0)), Size(10, 10))

    assert fitted.mode == "RGB"
    assert fitted.getpixel((0, 0)) == (255, 255, 255)


def test_flatten_still_puts_transparency_on_white_when_asked():
    """It is not gone -- it moved to the end, where the format decides."""
    flattened = flatten_to_white(Image.new("RGBA", (4, 4), (0, 0, 0, 0)))

    assert flattened.mode == "RGB"
    assert flattened.getpixel((0, 0)) == (255, 255, 255)


def test_flatten_takes_another_colour():
    flattened = flatten_to_white(Image.new("RGBA", (4, 4), (0, 0, 0, 0)), (255, 0, 0))

    assert flattened.getpixel((0, 0)) == (255, 0, 0)


def test_has_alpha_knows_the_modes_apart():
    from image_convertor.converter import has_alpha

    assert has_alpha(Image.new("RGBA", (2, 2)))
    assert has_alpha(Image.new("LA", (2, 2)))
    assert not has_alpha(Image.new("RGB", (2, 2)))
    assert not has_alpha(Image.new("L", (2, 2)))


def test_blur_keeps_the_alpha_channel():
    """Blurring the alpha too is what a blur means -- the edge softens with
    the picture rather than staying a hard cut-out."""
    from image_convertor.effects import Blur

    clear = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for x in range(8, 16):
        for y in range(16):
            clear.putpixel((x, y), (200, 30, 30, 255))

    blurred = Blur(3).apply(clear)
    alpha = set(blurred.getchannel("A").tobytes())

    assert blurred.mode == "RGBA"
    assert any(0 < value < 255 for value in alpha), "the alpha edge stayed hard"
