"""The conversion itself: flatten, fit, apply the effects, write the file.

Nothing here talks to the user -- cli.py does that. Everything is a plain
function over a Pillow image so it can be tested without a folder of files.

The effects themselves live in effects.py; this module owns the pipeline
they run inside, which is the part that does not change when one is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import formats
from .effects import Effect, apply_effects
from .formats import Format

# What we will try to open. Pillow reads more than this, but these are the ones
# worth walking an input folder for; anything else is skipped with a message
# rather than silently.
SUPPORTED_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".ico",
}

WHITE = (255, 255, 255)


@dataclass(frozen=True)
class Size:
    """A width x height box the image has to fit inside."""

    width: int
    height: int

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


def parse_size(text: str) -> Size | None:
    """Read "WIDTHxHEIGHT" from what the user typed.

    Empty (they just pressed enter) means "no resizing" and gives None, which
    is a different thing from a bad value -- that raises.
    """
    text = text.strip().lower().replace(" ", "")
    if not text:
        return None

    for separator in ("x", "*", ","):
        if separator in text:
            left, _, right = text.partition(separator)
            break
    else:
        raise ValueError(f"Expected something like 320x240, got {text!r}")

    try:
        width, height = int(left), int(right)
    except ValueError:
        raise ValueError(f"Expected whole numbers, got {text!r}") from None

    if width <= 0 or height <= 0:
        raise ValueError(f"Width and height must be positive, got {text!r}")

    return Size(width, height)


def flatten_to_white(image: Image.Image) -> Image.Image:
    """Drop transparency onto a white background.

    Straight to RGB would keep the colour of fully transparent pixels, which in
    a PNG is usually black -- so a logo with a clear background comes out as a
    black rectangle. Compositing is what makes transparent mean white.
    """
    if image.mode == "P" and "transparency" in image.info:
        image = image.convert("RGBA")

    if image.mode in ("RGBA", "LA"):
        image = image.convert("RGBA")
        background = Image.new("RGBA", image.size, WHITE + (255,))
        return Image.alpha_composite(background, image).convert("RGB")

    return image.convert("RGB")


def fit_into_box(image: Image.Image, box: Size) -> Image.Image:
    """Shrink to fit inside the box, keeping the ratio, centred on white.

    The scale is the smaller of the two ratios, so the whole image lands inside
    the box; a box with a different ratio leaves white bands on two sides
    rather than a stretched image. Images already smaller than the box are not
    blown up -- they are just centred.
    """
    scale = min(box.width / image.width, box.height / image.height, 1.0)

    # At least one pixel each way: a very wide image shrunk hard would
    # otherwise round its height to zero and fail to resize at all.
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))

    if (width, height) != image.size:
        image = image.resize((width, height), Image.LANCZOS)

    if (width, height) == (box.width, box.height):
        return image

    canvas = Image.new("RGB", (box.width, box.height), WHITE)
    canvas.paste(image, ((box.width - width) // 2, (box.height - height) // 2))
    return canvas


@dataclass(frozen=True)
class Converted:
    """What happened to one image.

    `size` is the file that was written and `original` the file that was read;
    when a box was asked for they differ by the white padding as well as by
    any shrinking, which is why `shrunk` is recorded rather than inferred.
    """

    size: Size
    original: Size
    shrunk: bool

    @property
    def too_small_to_shrink(self) -> bool:
        """Asked to fit a box it already fitted inside.

        Worth saying out loud: the file comes out at the size asked for, so
        nothing looks wrong, but it is padding rather than detail -- usually a
        sign the box is bigger than the source material.
        """
        return not self.shrunk and self.size != self.original


def convert_image(
    source: Path,
    destination: Path,
    box: Size | None = None,
    effects: tuple[Effect, ...] = (),
    fmt: Format | None = None,
) -> Converted:
    """Convert one file and write it.

    The format decides the container only; the effects decide the depth --
    `monochrome` is what makes an image 1-bit. With no format given it is
    taken from the source, which is what "the same as the input" means.

    The order is flatten, fit, then the effects -- and it is that way round for
    a reason. Flattening first means an effect never has to think about an
    alpha channel. Fitting before the effects rather than after means a blur
    radius or a noise amount is in output pixels, which is the only size the
    person choosing the number can see; applied first, most of the effect would
    be thrown away by the shrink that followed.
    """
    if fmt is None:
        fmt = formats.for_source(source)

    with Image.open(source) as opened:
        image = flatten_to_white(opened)

    original = Size(*image.size)

    if box is not None:
        image = fit_into_box(image, box)

    image = apply_effects(image, effects)

    formats.save(image, destination, fmt)

    written = Size(*image.size)
    shrunk = written.width < original.width or written.height < original.height
    return Converted(size=written, original=original, shrunk=shrunk)


def find_images(folder: Path) -> list[Path]:
    """Every image directly inside the folder, in a predictable order."""
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
