"""The image formats that can be written, and which ones can hold one bit.

The format and the colour depth are two separate questions, and the app used
to answer both with one answer: everything came out as a 1-bit BMP. Now the
effects decide the depth -- `monochrome` is what makes an image 1-bit -- and
this module decides the container.

Which is why the interesting thing here is not the list of formats. It is that
**Pillow does not refuse the combinations that do not work.** Saving a 1-bit
image as JPEG does not raise; it quietly writes an 8-bit grey JPEG, and the
dithered dots come back with ringing around every one of them. Nothing in the
traceback tells you, because there is no traceback. So the refusing is done
here, before anything is written.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class Format:
    """One output format.

    `keeps_one_bit` is about what comes back out, not about what Pillow
    accepts going in -- every format below accepts a 1-bit image, and only
    three of them give one back. GIF and WebP store it as grey or as a
    palette, which looks identical because there are still only two levels in
    it; JPEG is the one where it stops looking identical.
    """

    name: str
    suffix: str
    pillow: str
    keeps_one_bit: bool
    lossy: bool
    #: Whether transparency survives being written in this format. Measured,
    #: not read off a spec sheet: BMP and GIF both *accept* an RGBA image and
    #: hand back one without alpha, which is the silent case this flag exists
    #: to catch.
    keeps_alpha: bool = False
    note: str = ""


PNG = Format("png", ".png", "PNG", keeps_one_bit=True, lossy=False, keeps_alpha=True)
TIFF = Format("tiff", ".tiff", "TIFF", keeps_one_bit=True, lossy=False, keeps_alpha=True)
BMP = Format(
    "bmp", ".bmp", "BMP",
    keeps_one_bit=True,
    lossy=False,
    note="no transparency: clear areas are filled with white",
)
GIF = Format(
    "gif", ".gif", "GIF",
    keeps_one_bit=False,
    lossy=False,
    note="two levels survive; no transparency, clear areas are filled white",
)
WEBP = Format(
    "webp", ".webp", "WEBP",
    keeps_one_bit=False,
    lossy=False,
    keeps_alpha=True,
    note="written lossless when the image has two levels, so the dots survive",
)
JPEG = Format(
    "jpg", ".jpg", "JPEG",
    keeps_one_bit=False,
    lossy=True,
    note="no transparency, and cannot hold one bit -- see why below",
)

REGISTRY: dict[str, Format] = {
    fmt.name: fmt for fmt in (PNG, JPEG, BMP, GIF, TIFF, WEBP)
}

# What an input suffix means, for the default -- "the same as the input".
# More suffixes than formats, because .jpeg and .jpg are one format and so
# are .tif and .tiff.
BY_SUFFIX: dict[str, Format] = {
    ".png": PNG,
    ".jpg": JPEG,
    ".jpeg": JPEG,
    ".bmp": BMP,
    ".gif": GIF,
    ".tif": TIFF,
    ".tiff": TIFF,
    ".webp": WEBP,
}

# An input format nothing can be written back to. .ico reads fine and Pillow
# will write one, but what it writes at an arbitrary size does not read back,
# so "the same as the input" has to mean something else for these.
FALLBACK = PNG


def resolve(name: str) -> Format:
    """The format the user asked for, by name."""
    name = name.strip().lower().lstrip(".")
    if name in ("jpeg", "tif"):  # the spellings that are the same format
        name = {"jpeg": "jpg", "tif": "tiff"}[name]

    found = REGISTRY.get(name)
    if found is None:
        known = ", ".join(sorted(REGISTRY))
        raise ValueError(f"Unknown format {name!r} -- known formats are: {known}")
    return found


def for_source(source: Path) -> Format:
    """What "the same as the input" means for this file.

    A suffix nothing can be written back to falls back to PNG rather than
    failing: the request was "leave the format alone", and the nearest
    honest answer to that for a .ico is a lossless format that holds
    everything the .ico did.
    """
    return BY_SUFFIX.get(source.suffix.lower(), FALLBACK)


def two_levels(image: Image.Image) -> bool:
    """Whether the image is pure black and pure white, and nothing else.

    Asked of the pixels rather than of the mode, because monochrome no longer
    always produces mode "1": an image with transparency comes out of it as
    "LA", since one bit has no room for a third state. Both are the thing a
    lossy format ruins.

    **Both extremes have to be present.** "Two levels or fewer" was the first
    version of this and it was wrong: a flat colour has one level, so an
    ordinary red square counted as a dither and JPEG was refused for it. What
    makes a dither unsurvivable is the hard edge between 0 and 255 next to each
    other, and an image without both simply does not have one.

    `getcolors` returns None past its limit, which makes this cheap on a
    photograph -- it stops counting almost immediately.
    """
    counted = image.convert("L").getcolors(3)
    if counted is None:
        return False
    return {value for _, value in counted} == {0, 255}


def refuse_reason(fmt: Format, image: Image.Image) -> str | None:
    """Why this image must not be written in this format, or None if it may.

    One rule, and it earns the whole module. Everything else Pillow either
    handles or degrades in a way `save` below puts right.
    """
    if fmt.lossy and two_levels(image):
        return (
            f"{fmt.name} is lossy and cannot hold a two-level image: the dots "
            f"of a dither come back with ringing round every one of them. "
            f"Pillow writes it anyway, as 8-bit grey, which is why this stops "
            f"here. Use png, bmp or tiff, or drop the monochrome effect."
        )
    return None


def save(image: Image.Image, destination: Path, fmt: Format) -> None:
    """Write the image, in the one way that format wants it.

    Refuses first -- see `refuse_reason` -- then puts right the two things
    Pillow does quietly and wrongly: dropping an alpha channel a format cannot
    hold, and dropping one it can.
    """
    reason = refuse_reason(fmt, image)
    if reason is not None:
        raise ValueError(reason)

    from .converter import flatten_to_white, has_alpha

    if has_alpha(image) and not fmt.keeps_alpha:
        # BMP and GIF do not refuse an RGBA image -- they write one without
        # the alpha, keeping whatever colour was hiding under the transparent
        # pixels, which in a PNG is usually black. So a logo with a clear
        # background would come out as a black rectangle. Compositing onto
        # white is what "no transparency" has to mean.
        image = flatten_to_white(image)

        # Flattening leaves 8-bit grey behind, even when what went in had two
        # levels: a monochrome image with transparency is carried as "LA",
        # since one bit has no room for a third state, and dropping the alpha
        # gives back the two levels and the room. So take the bit back.
        if two_levels(image):
            image = image.convert("1")

    options: dict[str, object] = {}

    if fmt is WEBP:
        if image.mode == "LA":
            # WebP writes an LA image as RGB and throws the alpha away
            # without a word. RGBA it keeps.
            image = image.convert("RGBA")
        if two_levels(image):
            # WebP is lossy by default, and lossy plus two levels is the same
            # problem JPEG is refused for. Lossless costs nothing here.
            options["lossless"] = True

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format=fmt.pillow, **options)


def destination_for(source: Path, folder: Path, fmt: Format) -> Path:
    """Where this source lands, named for the format it is written in."""
    return folder / (source.stem + fmt.suffix)
