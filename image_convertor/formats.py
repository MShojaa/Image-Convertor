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
    note: str = ""


PNG = Format("png", ".png", "PNG", keeps_one_bit=True, lossy=False)
BMP = Format("bmp", ".bmp", "BMP", keeps_one_bit=True, lossy=False)
TIFF = Format("tiff", ".tiff", "TIFF", keeps_one_bit=True, lossy=False)
GIF = Format(
    "gif", ".gif", "GIF",
    keeps_one_bit=False,
    lossy=False,
    note="stored as grey; two levels in, two levels out",
)
WEBP = Format(
    "webp", ".webp", "WEBP",
    keeps_one_bit=False,
    lossy=False,
    note="written lossless when the image is 1-bit, so the dots survive",
)
JPEG = Format(
    "jpg", ".jpg", "JPEG",
    keeps_one_bit=False,
    lossy=True,
    note="cannot hold one bit -- see why below",
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


def refuse_reason(fmt: Format, mode: str) -> str | None:
    """Why this image must not be written in this format, or None if it may.

    One rule today, and it earns the whole module. Everything else Pillow
    handles or degrades harmlessly.
    """
    if mode == "1" and fmt.lossy:
        return (
            f"{fmt.name} is lossy and cannot hold a 1-bit image: the dots of a "
            f"dither come back with ringing round every one of them. Pillow "
            f"writes it anyway, as 8-bit grey, which is why this stops here. "
            f"Use --format png, bmp or tiff, or drop the monochrome effect."
        )
    return None


def save(image: Image.Image, destination: Path, fmt: Format) -> None:
    """Write the image, in the one way that format wants it.

    Refuses first -- see `refuse_reason` -- and then does whatever that format
    needs that Pillow will not do by itself.
    """
    reason = refuse_reason(fmt, image.mode)
    if reason is not None:
        raise ValueError(reason)

    options: dict[str, object] = {}
    if fmt is WEBP and image.mode == "1":
        # WebP is lossy by default, and lossy plus two levels is the same
        # problem JPEG is refused for. Lossless costs nothing on an image with
        # two colours in it.
        options["lossless"] = True

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format=fmt.pillow, **options)


def destination_for(source: Path, folder: Path, fmt: Format) -> Path:
    """Where this source lands, named for the format it is written in."""
    return folder / (source.stem + fmt.suffix)
