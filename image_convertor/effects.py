"""The effects a conversion can apply, and the order they run in.

An effect is a small frozen value that knows how to apply itself to a Pillow
image. They are values rather than functions so that a chosen set of them can
be parsed, printed back, compared in a test and handed across to a front end
without carrying a closure around.

Two things are deliberately not the caller's problem:

**The order is fixed**, and it is the `order` field, not the order they were
named in. Most orderings are simply wrong -- noise after a hard cut adds grey
to an image that has only two levels left, and blur after it does the same --
so the pipeline sorts rather than trusting the command line. Letting the order
be chosen is a later flag, if it is ever wanted; it is not the first version.

**Each one is applied once.** Naming an effect twice is a mistake rather than a
request for two passes: `apply_effects` keeps the last of each kind, so a
front end that lets someone change their mind does not have to remember to take
the previous answer out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from PIL import Image, ImageFilter

# Mid grey: the hard cut has to split somewhere, and halfway is the only
# choice that does not lean light or dark before seeing the image.
DEFAULT_THRESHOLD = 128

# One pixel of blur. Big enough to see on anything, small enough not to
# destroy a small image -- and the radii below 1 are the useful ones there,
# which is why this is a float and not an int.
DEFAULT_BLUR_RADIUS = 1.0


@dataclass(frozen=True)
class Effect:
    """One step of the conversion.

    Subclasses set `name` (what the user types) and `order` (where it runs),
    and implement `apply`. The `order` numbers are spaced so that something new
    can be slotted between two existing ones without renumbering.
    """

    name: ClassVar[str] = ""
    order: ClassVar[int] = 0

    def apply(self, image: Image.Image) -> Image.Image:
        raise NotImplementedError

    def described(self) -> str:
        """How this effect would be written on the command line."""
        return self.name


@dataclass(frozen=True)
class Blur(Effect):
    """Gaussian blur, in output pixels.

    It runs before monochrome, which is the only ordering that does anything:
    a 1-bit image has no levels between black and white to smear, so blurring
    one gives back the same image.

    Blur into a hard cut is the pairing worth knowing about -- it is how a
    threshold gets a soft edge instead of a jagged one. Blur into a dither
    mostly cancels out, because dithering is already scattering dots to fake
    the grey levels the blur just created.
    """

    radius: float = DEFAULT_BLUR_RADIUS

    name: ClassVar[str] = "blur"
    order: ClassVar[int] = 10

    def __post_init__(self) -> None:
        if self.radius < 0:
            raise ValueError(f"A blur radius cannot be negative -- got {self.radius}")

    def apply(self, image: Image.Image) -> Image.Image:
        if self.radius == 0:
            return image
        return image.filter(ImageFilter.GaussianBlur(self.radius))

    def described(self) -> str:
        return f"{self.name}:{self.radius:g}"


@dataclass(frozen=True)
class Monochrome(Effect):
    """Down to one bit per pixel.

    With no threshold Pillow dithers (Floyd-Steinberg), which scatters black
    dots to fake the grey levels a photograph needs. A threshold is the hard
    cut: every pixel lighter than it turns white and the rest black, keeping
    flat areas flat -- which is what line art, icons and text want, because
    dithering turns a flat grey fill into speckle.

    It runs last, always. Everything else works on grey levels this step
    throws away.
    """

    threshold: int | None = None

    name: ClassVar[str] = "monochrome"
    order: ClassVar[int] = 90

    def __post_init__(self) -> None:
        if self.threshold is not None and not 0 <= self.threshold <= 255:
            raise ValueError(
                f"A threshold is a grey level, 0 to 255 -- got {self.threshold}"
            )

    def apply(self, image: Image.Image) -> Image.Image:
        grey = image.convert("L")
        if self.threshold is None:
            return grey.convert("1")
        return grey.point(lambda value: 255 if value >= self.threshold else 0, mode="1")

    def described(self) -> str:
        if self.threshold is None:
            return self.name
        return f"{self.name}:{self.threshold}"


def apply_effects(image: Image.Image, effects: tuple[Effect, ...]) -> Image.Image:
    """Run the effects over the image, in their own order, one of each."""
    for effect in order_effects(effects):
        image = effect.apply(image)
    return image


def order_effects(effects: tuple[Effect, ...]) -> tuple[Effect, ...]:
    """The effects as they will actually run: deduplicated, then sorted.

    Last of each kind wins, because a front end that lets someone revise an
    answer produces the new one after the old one. Sorting is stable, so two
    different effects sharing an `order` keep the order they were given -- no
    two do today, and if two ever did, silently reordering them would be worse
    than leaving them alone.
    """
    kept: dict[str, Effect] = {}
    for effect in effects:
        kept[effect.name] = effect
    return tuple(sorted(kept.values(), key=lambda effect: effect.order))


# Every effect the app knows, by the name the user types. Adding one here is
# all it takes to make it parseable -- there is no second list to update.
REGISTRY: dict[str, type[Effect]] = {
    Blur.name: Blur,
    Monochrome.name: Monochrome,
}


def parse_effect(text: str) -> Effect:
    """Read one effect from "name" or "name:argument".

    The argument is the effect's one setting -- a threshold for monochrome --
    and leaving it off takes that effect's default.
    """
    text = text.strip().lower()
    if not text:
        raise ValueError("Expected an effect name")

    name, _, argument = text.partition(":")
    name = name.strip()
    argument = argument.strip()

    kind = REGISTRY.get(name)
    if kind is None:
        known = ", ".join(sorted(REGISTRY))
        raise ValueError(f"Unknown effect {name!r} -- known effects are: {known}")

    if not argument:
        return kind()

    return kind(_parse_argument(kind, argument))


def _parse_argument(kind: type[Effect], argument: str) -> object:
    """Turn the text after the colon into whatever that effect takes.

    Each effect declares the type through its annotation rather than through a
    parser of its own; there is one setting per effect and they are all
    numbers, so a table here would be a table of one-line entries.
    """
    if kind is Monochrome:
        try:
            return int(argument)
        except ValueError:
            raise ValueError(
                f"A monochrome threshold is a whole number -- got {argument!r}"
            ) from None

    if kind is Blur:
        try:
            return float(argument)
        except ValueError:
            raise ValueError(
                f"A blur radius is a number of pixels -- got {argument!r}"
            ) from None

    raise ValueError(f"{kind.name} takes no argument, got {argument!r}")


def describe(effects: tuple[Effect, ...]) -> str:
    """The effects as a line of prose, in the order they will run."""
    ordered = order_effects(effects)
    if not ordered:
        return "no effects"
    return ", ".join(effect.described() for effect in ordered)
