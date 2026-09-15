"""The conversion itself: flatten, fit, threshold, write a 1-bit BMP.

Nothing here talks to the user -- cli.py does that. Everything is a plain
function over a Pillow image so it can be tested without a folder of files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# What we will try to open. Pillow reads more than this, but these are the ones
# worth walking an input folder for; anything else is skipped with a message
# rather than silently.
SUPPORTED_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".ico",
}

WHITE = (255, 255, 255)

# Mid grey: the hard cut has to split somewhere, and halfway is the only
# choice that does not lean light or dark before seeing the image.
DEFAULT_THRESHOLD = 128


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


def to_monochrome(image: Image.Image, threshold: int | None) -> Image.Image:
    """Down to one bit per pixel.

    With no threshold Pillow dithers (Floyd-Steinberg), which scatters black
    dots to fake the grey levels a photograph needs. A threshold is the hard
    cut: every pixel lighter than it turns white and the rest black, keeping
    flat areas flat -- which is what line art, icons and text want, because
    dithering turns a flat grey fill into speckle.
    """
    grey = image.convert("L")
    if threshold is None:
        return grey.convert("1")
    return grey.point(lambda value: 255 if value >= threshold else 0, mode="1")


def convert_image(
    source: Path,
    destination: Path,
    box: Size | None = None,
    threshold: int | None = None,
) -> Size:
    """Convert one file and write it as a 1-bit BMP. Returns the size written."""
    with Image.open(source) as opened:
        image = flatten_to_white(opened)

    if box is not None:
        image = fit_into_box(image, box)

    image = to_monochrome(image, threshold)

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="BMP")
    return Size(*image.size)


def find_images(folder: Path) -> list[Path]:
    """Every image directly inside the folder, in a predictable order."""
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
