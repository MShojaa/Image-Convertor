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

import random
from dataclasses import dataclass
from typing import ClassVar

from PIL import Image, ImageChops, ImageFilter

# Mid grey: the hard cut has to split somewhere, and halfway is the only
# choice that does not lean light or dark before seeing the image.
DEFAULT_THRESHOLD = 128

# One pixel of blur. Big enough to see on anything, small enough not to
# destroy a small image -- and the radii below 1 are the useful ones there,
# which is why this is a float and not an int.
DEFAULT_BLUR_RADIUS = 1.0

# Enough noise to see without burying the picture: a tenth of the range,
# either way, per pixel.
DEFAULT_NOISE_AMOUNT = 25

# Noise with no seed makes a run that cannot be reproduced and a test that
# can only assert that something changed. Seeding from the clock would be
# the usual default and is the wrong one here: converting the same folder
# twice should give the same files. Pass a different seed to get different
# noise -- that is what the number is for.
DEFAULT_NOISE_SEED = 0


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
class Noise(Effect):
    """Uniform noise, added to every pixel, in whatever colour the image is.

    Uniform rather than Gaussian: it is one number to expose and one number to
    reason about -- every pixel moves by at most `amount`, either way -- where
    Gaussian needs a standard deviation and still has no bound. Film grain is
    the argument for Gaussian, and this is not a film grain tool.

    **The same noise goes on every channel**, which is what keeps a colour
    image colour. Rolling a separate number per channel moves the channels
    apart from each other, and moving R away from G *is* a change of hue: a
    grey wall comes back speckled pink and green. One value per pixel added to
    all three shifts each pixel lighter or darker and leaves its colour alone,
    which is what noise on a photograph is meant to look like.

    Alpha is left out of it. Noising transparency would make a clean edge
    fizzle, and nothing about "add noise" says the shape should change.

    It used to convert to grey first, on the grounds that monochrome came next
    and would throw the colour away anyway -- true only when monochrome is
    actually picked, which it no longer always is.

    It runs after blur. Blur over noise is just a quieter noise, which is not
    what either effect says it does.
    """

    amount: int = DEFAULT_NOISE_AMOUNT
    seed: int = DEFAULT_NOISE_SEED

    name: ClassVar[str] = "noise"
    order: ClassVar[int] = 20

    def __post_init__(self) -> None:
        if not 0 <= self.amount <= 255:
            raise ValueError(
                f"A noise amount is a grey range, 0 to 255 -- got {self.amount}"
            )

    def apply(self, image: Image.Image) -> Image.Image:
        if self.amount == 0:
            return image

        # A palette has no channels to add to; RGB is the honest reading of
        # one, and is what the rest of the pipeline works in anyway.
        if image.mode == "P":
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")
        elif image.mode == "1":
            # Two levels plus noise is two levels again -- adding to a 1-bit
            # image and staying 1-bit would do nothing at all.
            image = image.convert("L")

        noise = self._noise_for(image.size)

        if image.mode == "L":
            return self._add(image, noise)

        # The same noise on every colour channel, and none on alpha.
        bands = [
            band if name == "A" else self._add(band, noise)
            for band, name in zip(image.split(), image.getbands())
        ]
        return Image.merge(image.mode, bands)

    def _noise_for(self, size: tuple[int, int]) -> Image.Image:
        """One channel of noise, 0..2*amount, the same every run for a seed.

        A whole-image operation, not a loop over pixels. The obvious version --
        read a pixel, add a random number, write it back -- is a Python loop
        per pixel, which is fine on an icon and takes tens of seconds on a
        photograph. This builds the noise as an image and lets Pillow add it
        in C.

        A generator of our own rather than the module-level one: seeding
        `random` globally would reach into whatever else the process is doing,
        which in the tests is pytest.
        """
        rolls = random.Random(self.seed)
        span = 2 * self.amount + 1
        noise = Image.frombytes("L", size, rolls.randbytes(size[0] * size[1]))
        return noise.point(lambda value: value * span // 256)

    def _add(self, band: Image.Image, noise: Image.Image) -> Image.Image:
        """One channel plus the noise, shifted to run either way and clamped.

        ImageChops.add computes (a + b) + offset and clamps, which is the whole
        reason for using it: 250 + 30 has to be white, not 24.
        """
        return ImageChops.add(band, noise, scale=1.0, offset=-self.amount)

    def described(self) -> str:
        if self.seed == DEFAULT_NOISE_SEED:
            return f"{self.name}:{self.amount}"
        return f"{self.name}:{self.amount}:{self.seed}"


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

    An image carrying transparency comes back as "LA" rather than "1", because
    one bit has no room for a third state. It is the same two levels either
    way.
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
        alpha = image.getchannel("A") if image.mode in ("RGBA", "LA", "La") else None

        grey = image.convert("L")
        if self.threshold is None:
            black_and_white = grey.convert("1")
        else:
            black_and_white = grey.point(
                lambda value: 255 if value >= self.threshold else 0, mode="1"
            )

        if alpha is None:
            return black_and_white

        # One bit has no room for a third state, so an image that has to keep
        # its transparency comes back as "LA": the same two levels, in a mode
        # that has somewhere to put the alpha. `formats.two_levels` is what
        # notices it is still black and white.
        return Image.merge("LA", (black_and_white.convert("L"), alpha))

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
    Noise.name: Noise,
    Monochrome.name: Monochrome,
}


def parse_effect(text: str) -> Effect:
    """Read one effect from "name", "name:argument" or "name:argument:...".

    The arguments are that effect's settings in the order it declares them --
    a threshold for monochrome, a radius for blur, an amount and then a seed
    for noise -- and leaving any of them off takes the default.
    """
    text = text.strip().lower()
    if not text:
        raise ValueError("Expected an effect name")

    name, _, rest = text.partition(":")
    name = name.strip()

    kind = REGISTRY.get(name)
    if kind is None:
        known = ", ".join(sorted(REGISTRY))
        raise ValueError(f"Unknown effect {name!r} -- known effects are: {known}")

    # An empty piece means "the default for that one", so "noise::7" is the
    # default amount with seed 7 rather than an error.
    pieces = [piece.strip() for piece in rest.split(":")] if rest else []
    while pieces and pieces[-1] == "":
        pieces.pop()

    settings = SETTINGS[kind]
    if len(pieces) > len(settings):
        expected = ", ".join(label for label, _, _ in settings) or "nothing"
        raise ValueError(
            f"{name} takes {expected} -- got {len(pieces)} values in {text!r}"
        )

    arguments = {}
    for piece, (label, convert, description) in zip(pieces, settings):
        if piece == "":
            continue
        try:
            arguments[label] = convert(piece)
        except ValueError:
            raise ValueError(f"{description} -- got {piece!r}") from None

    return kind(**arguments)


# What each effect takes after its name, in order: the field, how to read it,
# and the sentence to say when it will not read. One table rather than a
# branch per effect, so adding an effect is adding a row.
SETTINGS: dict[type[Effect], tuple[tuple[str, object, str], ...]] = {
    Blur: (("radius", float, "A blur radius is a number of pixels"),),
    Noise: (
        ("amount", int, "A noise amount is a whole number of grey levels"),
        ("seed", int, "A noise seed is a whole number"),
    ),
    Monochrome: (("threshold", int, "A monochrome threshold is a whole number"),),
}


def describe(effects: tuple[Effect, ...]) -> str:
    """The effects as a line of prose, in the order they will run."""
    ordered = order_effects(effects)
    if not ordered:
        return "no effects"
    return ", ".join(effect.described() for effect in ordered)
