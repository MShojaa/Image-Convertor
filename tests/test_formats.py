"""Which formats can be written, and which pairings are refused.

The pairing rule is the reason this file matters. Pillow does not raise when
asked to save a 1-bit image as JPEG -- it writes 8-bit grey and says nothing --
so these are the checks that the refusal exists at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from image_convertor import formats
from image_convertor.converter import Size, convert_image
from image_convertor.effects import Monochrome


# --- naming a format -----------------------------------------------------

@pytest.mark.parametrize(
    "name, expected",
    [
        ("png", formats.PNG),
        ("PNG", formats.PNG),
        (" .png ", formats.PNG),
        ("jpg", formats.JPEG),
        ("jpeg", formats.JPEG),   # the same format, spelled the other way
        ("tif", formats.TIFF),
        ("tiff", formats.TIFF),
    ],
)
def test_a_format_can_be_named_the_ways_people_write_it(name, expected):
    assert formats.resolve(name) is expected


def test_an_unknown_format_names_the_known_ones():
    with pytest.raises(ValueError) as raised:
        formats.resolve("heic")

    message = str(raised.value)
    assert "heic" in message
    for name in formats.REGISTRY:
        assert name in message


def test_every_registered_format_agrees_with_its_key():
    for name, fmt in formats.REGISTRY.items():
        assert fmt.name == name
        assert fmt.suffix.startswith(".")


# --- the default: the same as the input ----------------------------------

@pytest.mark.parametrize(
    "filename, expected",
    [
        ("a.png", formats.PNG),
        ("a.PNG", formats.PNG),
        ("a.jpg", formats.JPEG),
        ("a.jpeg", formats.JPEG),
        ("a.tif", formats.TIFF),
        ("a.bmp", formats.BMP),
        ("a.gif", formats.GIF),
        ("a.webp", formats.WEBP),
    ],
)
def test_the_input_suffix_decides_the_output_format(filename, expected):
    assert formats.for_source(Path(filename)) is expected


def test_a_format_that_cannot_be_written_back_falls_back_to_png():
    """.ico reads fine; what Pillow writes at an arbitrary size does not read."""
    assert formats.for_source(Path("favicon.ico")) is formats.PNG


def test_the_destination_is_named_for_the_format_written(tmp_path):
    landed = formats.destination_for(Path("photo.jpg"), tmp_path, formats.PNG)

    assert landed == tmp_path / "photo.png"


# --- the refusal ---------------------------------------------------------

def dithered(size=(8, 8)):
    """An image with both extremes in it -- what a dither actually is."""
    image = Image.new("1", size, 1)
    for x in range(0, size[0], 2):
        for y in range(size[1]):
            image.putpixel((x, y), 0)
    return image


def test_a_dither_as_jpeg_is_refused_with_the_way_out():
    reason = formats.refuse_reason(formats.JPEG, dithered())

    assert reason is not None
    assert "png" in reason  # it says what to do instead


@pytest.mark.parametrize("fmt", [formats.PNG, formats.BMP, formats.TIFF])
def test_the_lossless_formats_take_a_dither(fmt):
    assert formats.refuse_reason(fmt, dithered()) is None


@pytest.mark.parametrize("fmt", list(formats.REGISTRY.values()))
def test_no_format_refuses_an_ordinary_colour_image(fmt):
    assert formats.refuse_reason(fmt, Image.new("RGB", (8, 8), (200, 30, 30))) is None


def test_a_flat_colour_is_not_mistaken_for_a_dither():
    """The first version of the rule was "two levels or fewer", so a flat red
    square counted as a dither and jpg was refused for it."""
    for colour in ((200, 30, 30), (255, 255, 255), (0, 0, 0)):
        flat = Image.new("RGB", (8, 8), colour)
        assert formats.refuse_reason(formats.JPEG, flat) is None


def test_a_photograph_is_not_mistaken_for_a_dither():
    gradient = Image.new("L", (64, 1))
    for x in range(64):
        gradient.putpixel((x, 0), x * 4)

    assert formats.refuse_reason(formats.JPEG, gradient) is None


def test_saving_a_dither_as_jpeg_raises_rather_than_degrading(tmp_path):
    """Pillow would write 8-bit grey here and say nothing. This is the point."""
    with pytest.raises(ValueError):
        formats.save(dithered(), tmp_path / "x.jpg", formats.JPEG)

    assert not (tmp_path / "x.jpg").exists(), "it must refuse before writing"


# --- transparency -------------------------------------------------------

def transparent(size=(8, 8)):
    """Half opaque red, half clear."""
    image = Image.new("RGBA", size, (200, 30, 30, 255))
    for x in range(size[0] // 2):
        for y in range(size[1]):
            image.putpixel((x, y), (0, 0, 0, 0))
    return image


@pytest.mark.parametrize("fmt", [formats.PNG, formats.TIFF, formats.WEBP])
def test_the_formats_that_keep_alpha_really_do(fmt, tmp_path):
    path = tmp_path / ("x" + fmt.suffix)

    formats.save(transparent(), path, fmt)

    with Image.open(path) as result:
        assert result.mode in ("RGBA", "LA"), f"{fmt.name} lost the alpha"
        assert result.convert("RGBA").getchannel("A").getpixel((0, 0)) == 0


@pytest.mark.parametrize("fmt", [formats.BMP, formats.GIF, formats.JPEG])
def test_the_formats_that_cannot_hold_alpha_get_white_not_black(fmt, tmp_path):
    """Pillow does not refuse these -- BMP and GIF write the image without its
    alpha, keeping whatever colour hid under the clear pixels, which in a PNG
    is usually black. A logo with a clear background would come out as a black
    rectangle."""
    path = tmp_path / ("x" + fmt.suffix)

    formats.save(transparent(), path, fmt)

    with Image.open(path) as result:
        corner = result.convert("RGB").getpixel((0, 0))

    # Near-white rather than exactly white: jpg is lossy, and white next to a
    # hard edge comes back a couple of levels down. Black would be nowhere
    # near, which is the failure this is looking for.
    assert min(corner) > 240, f"{fmt.name} filled the clear area with {corner}"


def test_a_transparent_dither_still_reaches_png(tmp_path):
    """Monochrome on an image with alpha comes back as LA, not 1."""
    image = Image.merge("LA", (dithered().convert("L"), transparent().getchannel("A")))

    formats.save(image, tmp_path / "x.png", formats.PNG)

    with Image.open(tmp_path / "x.png") as result:
        assert result.mode == "LA"
        assert set(result.getchannel("L").tobytes()) == {0, 255}


def test_webp_does_not_quietly_drop_an_la_alpha(tmp_path):
    """WebP writes LA as RGB and says nothing, so it is converted first."""
    image = Image.merge("LA", (dithered().convert("L"), transparent().getchannel("A")))

    formats.save(image, tmp_path / "x.webp", formats.WEBP)

    with Image.open(tmp_path / "x.webp") as result:
        assert result.mode == "RGBA"
        assert result.getchannel("A").getpixel((0, 0)) == 0


def test_a_colour_image_still_saves_as_jpeg(tmp_path):
    formats.save(Image.new("RGB", (8, 8), (200, 30, 30)), tmp_path / "x.jpg", formats.JPEG)

    with Image.open(tmp_path / "x.jpg") as result:
        assert result.format == "JPEG"


# --- what actually comes back out ----------------------------------------

@pytest.mark.parametrize("fmt", [formats.PNG, formats.BMP, formats.TIFF])
def test_the_formats_that_claim_one_bit_really_give_it_back(fmt):
    assert fmt.keeps_one_bit


@pytest.mark.parametrize("fmt", [formats.PNG, formats.BMP, formats.TIFF])
def test_one_bit_survives_a_round_trip(fmt, tmp_path):
    source = Image.new("1", (8, 8))
    path = tmp_path / ("x" + fmt.suffix)

    formats.save(source, path, fmt)

    with Image.open(path) as result:
        assert result.mode == "1", f"{fmt.name} claims to keep one bit and did not"


@pytest.mark.parametrize("fmt", [formats.GIF, formats.WEBP])
def test_the_formats_that_do_not_keep_one_bit_still_keep_two_levels(fmt, tmp_path):
    """They store it as grey or palette, and it looks identical -- which is why
    they are allowed where JPEG is not."""
    source = Image.new("1", (8, 8))
    for x in range(4):
        for y in range(8):
            source.putpixel((x, y), 1)
    path = tmp_path / ("x" + fmt.suffix)

    formats.save(source, path, fmt)

    with Image.open(path) as result:
        levels = set(result.convert("L").tobytes())
    assert levels == {0, 255}


def test_webp_is_written_lossless_when_the_image_is_one_bit(tmp_path):
    """WebP defaults to lossy, and lossy plus two levels is JPEG's problem."""
    source = Image.new("1", (16, 16))
    for x in range(0, 16, 2):
        for y in range(16):
            source.putpixel((x, y), 1)   # a hard one-pixel stripe, the worst case

    formats.save(source, tmp_path / "x.webp", formats.WEBP)

    with Image.open(tmp_path / "x.webp") as result:
        assert set(result.convert("L").tobytes()) == {0, 255}


# --- through the whole conversion ----------------------------------------

def test_a_conversion_defaults_to_the_sources_format(tmp_path):
    source = tmp_path / "in.bmp"
    Image.new("RGB", (8, 8), (10, 20, 30)).save(source)

    convert_image(source, tmp_path / "out.bmp", None, ())

    with Image.open(tmp_path / "out.bmp") as result:
        assert result.format == "BMP"


def test_a_conversion_writes_the_format_it_is_given(tmp_path):
    source = tmp_path / "in.png"
    Image.new("RGB", (8, 8), (10, 20, 30)).save(source)

    convert_image(source, tmp_path / "out.gif", None, (), formats.GIF)

    with Image.open(tmp_path / "out.gif") as result:
        assert result.format == "GIF"


def test_monochrome_into_jpeg_is_refused_by_the_conversion(tmp_path):
    source = tmp_path / "in.jpg"
    # A gradient, so the dither has both extremes in it -- a flat square would
    # come out one level and there would be nothing to refuse.
    gradient = Image.new("L", (32, 8))
    for x in range(32):
        for y in range(8):
            gradient.putpixel((x, y), x * 8)
    gradient.convert("RGB").save(source)

    with pytest.raises(ValueError) as raised:
        convert_image(source, tmp_path / "out.jpg", None, (Monochrome(128),))

    assert "two-level" in str(raised.value)


def test_a_colour_jpeg_converts_to_a_jpeg(tmp_path):
    """No monochrome effect, no refusal -- the ordinary case still works."""
    source = tmp_path / "in.jpg"
    Image.new("RGB", (20, 16), (10, 20, 30)).save(source)

    written = convert_image(source, tmp_path / "out.jpg", Size(10, 10), ())

    assert written.size == Size(10, 10)
    with Image.open(tmp_path / "out.jpg") as result:
        assert result.format == "JPEG"
        assert result.mode == "RGB"
