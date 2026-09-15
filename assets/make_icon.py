#!/usr/bin/env python3
"""Draw the app icon, and write assets/icon.ico plus UI/logo.png.

Run it when the design changes; the results are committed, so a build does not
need it. It imports the app, so run it from the project root with the venv:

    .venv\\Scripts\\python.exe assets\\make_icon.py

The design is the thing the app does: a picture -- sun and hills, the glyph
everything uses for "image" -- with its right half run through the app's own
monochrome effect. The right side is real output from
`image_convertor.effects.Monochrome`, not an impression of one.

Three details, each of which the first version got wrong:

**The dither is coarse on purpose.** Dithering a smooth picture at full
resolution looks like the picture: correct, and invisible as an icon. The right
half is dithered at a twelfth of the size and scaled back up with NEAREST, so
the dots are big enough to read as dots.

**The tile and the picture are supersampled; the dither is not.** Pillow does
not antialias a rounded rectangle or a triangle, so those are drawn four times
too big and scaled down. Scaling a dither down averages it back into the grey
it came from -- the one thing that had to survive -- so it is computed at the
final size instead.

**There is a hard edge down the middle.** Without it the two halves blend and
the icon is just a picture; with it, the icon says what the app is for.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from image_convertor.effects import Monochrome  # noqa: E402

# The accent from docs/design-system.md, between its dark and light values so
# the tile sits on a dark taskbar and a light one.
TILE = (61, 130, 196)
WHITE = (255, 255, 255)

# Windows uses the 16 and 32 for the taskbar and title bar, 48 in Explorer,
# and 256 for the large view. The rest are there so nothing is ever scaled.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

SUPERSAMPLE = 4


def draw_icon(size: int) -> Image.Image:
    """One icon, at one size."""
    big = size * SUPERSAMPLE

    # The tile, supersampled so the corners come out smooth.
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    pen = ImageDraw.Draw(tile)
    pen.rounded_rectangle(
        (0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=TILE + (255,)
    )

    # The white frame the two halves sit in. Its inset is a fraction of the
    # size rather than a number of pixels, so every size looks the same.
    inset = int(big * 0.16)
    pen.rounded_rectangle(
        (inset, inset, big - inset - 1, big - inset - 1),
        radius=int(big * 0.07),
        fill=WHITE + (255,),
    )
    tile = tile.resize((size, size), Image.LANCZOS)

    panel_inset = round(size * 0.16)
    panel_size = size - panel_inset * 2
    if panel_size < 2:
        return tile

    picture = draw_picture(panel_size)
    panel = picture.convert("RGB")

    # The right half, dithered coarsely enough to see. Anything finer than
    # about a twelfth of the icon reads as grey rather than as dots.
    half = panel_size // 2
    right = picture.crop((half, 0, panel_size, panel_size))
    block = max(1, round(panel_size / 12))
    small = right.resize(
        (max(1, right.width // block), max(1, right.height // block)), Image.LANCZOS
    )
    dots = Monochrome(None).apply(small).convert("L")
    panel.paste(dots.resize(right.size, Image.NEAREST), (half, 0))

    # Round the panel's corners to the frame's, so no grey leaks past the white.
    mask = Image.new("L", (panel_size, panel_size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, panel_size - 1, panel_size - 1),
        radius=max(1, round(panel_size * 0.09)),
        fill=255,
    )
    tile.paste(panel, (panel_inset, panel_inset), mask)

    # The seam. Without it the halves blend into one picture and the icon
    # stops saying anything.
    seam = ImageDraw.Draw(tile)
    seam_x = panel_inset + panel_size // 2
    seam.line(
        [(seam_x, panel_inset), (seam_x, panel_inset + panel_size - 1)],
        fill=TILE + (255,),
        width=max(1, round(size / 48)),
    )
    return tile


def draw_picture(size: int) -> Image.Image:
    """Sun and hills, in grey, drawn big and scaled down.

    Supersampled because Pillow draws a polygon with hard edges, and a hillside
    is a diagonal -- the one shape that shows it most.
    """
    big = size * SUPERSAMPLE
    scene = Image.new("L", (big, big), 246)
    pen = ImageDraw.Draw(scene)

    # The sun sits on the seam, so each half of the icon shows half of the
    # same sun. That is the whole point of the split: not two pictures, one
    # picture rendered two ways.
    radius = big * 0.13
    centre = (big * 0.50, big * 0.27)
    pen.ellipse(
        (centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius),
        fill=110,
    )

    # Two hills, the near one darker, both running off the sides so the
    # picture reads as a landscape rather than as two triangles.
    # A hill either side of the seam, so neither half is left as empty sky.
    pen.polygon(
        [(big * -0.10, big), (big * 0.26, big * 0.50), (big * 0.62, big)],
        fill=150,
    )
    pen.polygon(
        [(big * 0.38, big), (big * 0.74, big * 0.58), (big * 1.10, big)],
        fill=60,
    )

    return scene.resize((size, size), Image.LANCZOS)


def main() -> int:
    icons = [draw_icon(size) for size in ICON_SIZES]

    ico = ROOT / "assets" / "icon.ico"
    icons[-1].save(ico, format="ICO", sizes=[(s, s) for s in ICON_SIZES])
    print(f"wrote {ico}")

    # The same mark for the window's header, at the size it is drawn.
    logo = ROOT / "UI" / "logo.png"
    draw_icon(96).save(logo, format="PNG")
    print(f"wrote {logo}")

    png = ROOT / "assets" / "icon.png"
    icons[-1].save(png, format="PNG")
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
