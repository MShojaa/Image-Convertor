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

from PIL import Image, ImageChops, ImageColor, ImageFilter, ImageOps

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

# Mid grey. Tinting with it is the identity -- black stays black, white stays
# white, and mid grey maps to itself -- so the default tint is plain grayscale
# and costs nothing to say.
NEUTRAL_TINT = (128, 128, 128)

# White, which is what a scanned page, a logo on a white card and an exported
# diagram all have as a background -- so it is what "make this transparent" is
# asking about nearly every time.
DEFAULT_KEY_COLOUR = (255, 255, 255)

# How far from that colour still counts, per channel. Tight: a jpg's "white"
# background wanders a few levels, and this is meant to catch that and not a
# pale grey that is part of the picture.
DEFAULT_TOLERANCE = 12

# How far the softened edge reaches, in pixels. One is enough to take the
# staircase off a keyed edge without eating into the picture.
SOFT_EDGE_RADIUS = 1.0

# Whether an effect leaves the transparent parts of an image alone. On by
# default: noise appearing in an area the user called transparent is a
# surprise, and a blur that softens a cut-out's silhouette is usually not what
# was being asked for. Turn it off to treat the whole rectangle as picture.
KEEP_CLEAR = True


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
        """How this effect would be written on the command line.

        Built from the same table that parses one, so the two cannot drift.
        A setting left at its default is written as nothing, and trailing
        nothings are dropped -- which is what makes the common case read as
        "blur" rather than "blur:1:yes".
        """
        import dataclasses

        defaults = {field.name: field.default for field in dataclasses.fields(type(self))}
        written = []
        for setting in SETTINGS.get(type(self), ()):
            value = getattr(self, setting.label)
            written.append(
                "" if value == defaults.get(setting.label) else setting.write(value)
            )

        while written and written[-1] == "":
            written.pop()

        return ":".join([self.name, *written]) if written else self.name


@dataclass(frozen=True)
class Transparent(Effect):
    """Make one colour see-through. White, unless told otherwise.

    Two ways to decide what counts as the colour, because neither is right for
    both kinds of image:

    **tolerance** takes anything within `tolerance` of it on every channel.
    This is the one to use on a photograph or a jpg, where the "white"
    background is never quite 255 -- compression moves it a few levels either
    way and an exact match finds almost none of it.

    **exact** takes only that colour and nothing else. Flat-colour PNGs, logos
    and exported diagrams key perfectly this way, and it cannot eat a pale part
    of the picture the way a tolerance can.

    `soft` is available to both, and does the same thing for both: it feathers
    the edge of the mask rather than widening the match. A hard key on an
    antialiased logo leaves a staircase, because the half-white pixels around
    the letters are either in or out; a one-pixel feather gives them partial
    alpha and the edge reads smooth.

    **Already-transparent pixels stay transparent.** The mask is combined with
    whatever alpha the image arrived with rather than replacing it, so running
    this twice, or after something else that made part of the image clear, does
    not undo the first one.

    It runs first, before everything. Keying after a blur would be keying the
    blur's own soft edges, and the point of doing it first is that every effect
    after it can be told to leave the transparent area alone.
    """

    colour: tuple[int, int, int] = DEFAULT_KEY_COLOUR
    match: str = "tolerance"
    tolerance: int = DEFAULT_TOLERANCE
    soft: bool = False

    name: ClassVar[str] = "transparent"
    order: ClassVar[int] = 5

    MATCHES: ClassVar[tuple[str, ...]] = ("tolerance", "exact")

    def __post_init__(self) -> None:
        if len(self.colour) != 3 or not all(0 <= part <= 255 for part in self.colour):
            raise ValueError(f"A colour is three values, 0 to 255 -- got {self.colour!r}")
        if self.match not in self.MATCHES:
            allowed = " or ".join(self.MATCHES)
            raise ValueError(f"Matching is {allowed} -- got {self.match!r}")
        if not 0 <= self.tolerance <= 255:
            raise ValueError(
                f"A tolerance is a distance in levels, 0 to 255 -- got {self.tolerance}"
            )

    def apply(self, image: Image.Image) -> Image.Image:
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # How far each pixel is from the key colour, per channel, taking the
        # worst of the three. The max rather than an average, because "within
        # 12 of white" has to mean all three channels are within 12 -- an
        # average would let a strong blue through on the strength of its red.
        rgb = image.convert("RGB")
        solid = Image.new("RGB", image.size, tuple(self.colour))
        red, green, blue = ImageChops.difference(rgb, solid).split()
        distance = ImageChops.lighter(ImageChops.lighter(red, green), blue)

        # Exact is a tolerance of zero. Keeping it as its own named choice
        # rather than asking people to work that out is the whole reason the
        # setting exists.
        reach = 0 if self.match == "exact" else self.tolerance
        keyed = distance.point(lambda value: 0 if value <= reach else 255, mode="L")

        if self.soft:
            # Feather the mask, not the match: a hard key on an antialiased
            # edge leaves a staircase, and widening the match instead would
            # eat further into the picture rather than smoothing what it cut.
            keyed = keyed.filter(ImageFilter.GaussianBlur(SOFT_EDGE_RADIUS))

        # Darker, not replace: a pixel that was already transparent stays
        # transparent whatever this mask says about its colour.
        image.putalpha(ImageChops.darker(image.getchannel("A"), keyed))
        return image



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
    keep_clear: bool = KEEP_CLEAR

    name: ClassVar[str] = "blur"
    order: ClassVar[int] = 10

    def __post_init__(self) -> None:
        if self.radius < 0:
            raise ValueError(f"A blur radius cannot be negative -- got {self.radius}")

    def apply(self, image: Image.Image) -> Image.Image:
        if self.radius == 0:
            return image
        return image.filter(ImageFilter.GaussianBlur(self.radius))



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
    keep_clear: bool = KEEP_CLEAR

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



@dataclass(frozen=True)
class Grayscale(Effect):
    """Take the colour out, optionally putting one colour back.

    The tint is a duotone, not a wash: the image's brightness is mapped onto a
    ramp that runs black -> tint -> white, so a reddish tint gives something
    sepia-like that keeps all of its shading. Multiplying by the colour instead
    would drag the highlights down with everything else and come out muddy.

    **The default tint is mid grey, and that is exactly plain grayscale.** The
    ramp black -> #808080 -> white is the identity, so the default needs no
    special case to mean "no tint" -- though it gets one anyway, to hand back a
    grey image rather than three identical channels.

    It runs after noise and before monochrome. Before monochrome because
    monochrome throws away everything this does; after noise because noise is
    monochromatic and tinting it with the picture is what keeps the grain part
    of the image rather than sat on top of it.
    """

    tint: tuple[int, int, int] = NEUTRAL_TINT
    keep_clear: bool = KEEP_CLEAR

    name: ClassVar[str] = "grayscale"
    order: ClassVar[int] = 50

    def __post_init__(self) -> None:
        if len(self.tint) != 3 or not all(0 <= part <= 255 for part in self.tint):
            raise ValueError(f"A tint is three values, 0 to 255 -- got {self.tint!r}")

    def apply(self, image: Image.Image) -> Image.Image:
        alpha = image.getchannel("A") if image.mode in ("RGBA", "LA", "La") else None
        grey = image.convert("L")

        if tuple(self.tint) == NEUTRAL_TINT:
            # The ramp would be the identity; skip it and stay in "L", which is
            # a third of the size and what monochrome wants next anyway.
            toned = grey
        else:
            toned = ImageOps.colorize(
                grey, black=(0, 0, 0), white=(255, 255, 255), mid=tuple(self.tint)
            )

        if alpha is None:
            return toned
        if toned.mode == "L":
            return Image.merge("LA", (toned, alpha))
        return Image.merge("RGBA", (*toned.split(), alpha))



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
    keep_clear: bool = KEEP_CLEAR

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



def apply_effects(image: Image.Image, effects: tuple[Effect, ...]) -> Image.Image:
    """Run the effects over the image, in their own order, one of each.

    An effect that asked to keep the clear areas clear gets its result put
    back through `restore_clear`, rather than every effect having to think
    about alpha itself. Doing it here also means a new effect gets the
    behaviour by declaring the field, and nothing else.
    """
    for effect in order_effects(effects):
        before = image
        image = effect.apply(image)
        if getattr(effect, "keep_clear", False):
            image = restore_clear(before, image)
    return image


def restore_clear(before: Image.Image, after: Image.Image) -> Image.Image:
    """Put back the transparency the effect was told not to touch.

    The alpha channel comes back exactly as it was -- so a blur softens the
    picture without softening the silhouette -- and the colour underneath is
    taken from whichever version the pixel was more visible in.

    That last part falls out of using the alpha as the mask, and it is the
    right answer rather than a convenient one: a pixel that is half
    transparent gets half the effect, so an antialiased edge does not end up
    with a hard line of untouched pixels along it.
    """
    if before.mode not in ("RGBA", "LA", "La"):
        return after

    alpha = before.getchannel("A")

    # Grey in, grey out: an effect that took the colour away should not have
    # it handed back by this.
    if after.mode in ("1", "L", "LA", "La"):
        kept = Image.composite(after.convert("L"), before.convert("L"), alpha)
        return Image.merge("LA", (kept, alpha))

    kept = Image.composite(after.convert("RGB"), before.convert("RGB"), alpha)
    return Image.merge("RGBA", (*kept.split(), alpha))


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
    Transparent.name: Transparent,
    Blur.name: Blur,
    Noise.name: Noise,
    Grayscale.name: Grayscale,
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
        expected = ", ".join(setting.label for setting in settings) or "nothing"
        raise ValueError(
            f"{name} takes {expected} -- got {len(pieces)} values in {text!r}"
        )

    arguments = {}
    for piece, setting in zip(pieces, settings):
        if piece == "":
            continue
        try:
            arguments[setting.label] = setting.parse(piece)
        except ValueError:
            raise ValueError(f"{setting.complaint} -- got {piece!r}") from None

    return kind(**arguments)


# What each effect takes after its name, in order: the field, how to read it,
# and the sentence to say when it will not read. One table rather than a
# branch per effect, so adding an effect is adding a row.
def parse_colour(text: str) -> tuple[int, int, int]:
    """A colour from a name or a hex value.

    Pillow's own parser, so "gray", "sepia"-ish hex, "#ccc" and "rgb(1,2,3)"
    all work without a table here of colours somebody would have to maintain.
    Any alpha in the value is dropped: this is a colour to tint with, not
    something to see through.
    """
    try:
        parsed = ImageColor.getrgb(text.strip())
    except ValueError:
        raise ValueError(
            f"A colour is a name like gray or a hex value like #8a5a2b"
        ) from None
    return tuple(parsed[:3])


TRUE_WORDS = ("yes", "true", "on", "1")
FALSE_WORDS = ("no", "false", "off", "0")


def parse_flag(text: str) -> bool:
    """A yes or a no, spelled any of the ways people spell them."""
    word = text.strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ValueError(f"A yes or no answer -- got {text!r}")


def choice_of(allowed: tuple[str, ...]):
    """A parser for one of a fixed set of words."""

    def parse(text: str) -> str:
        word = text.strip().lower()
        if word not in allowed:
            raise ValueError(f"One of {', '.join(allowed)} -- got {text!r}")
        return word

    return parse


def write_colour(value) -> str:
    return "#{:02x}{:02x}{:02x}".format(*tuple(value)[:3])


def write_flag(value) -> str:
    return "yes" if value else "no"


def write_number(value) -> str:
    # %g so a radius of 2.0 is "2": describe() is meant to be re-typable, and
    # nobody types the trailing zero.
    return "" if value is None else (f"{value:g}" if isinstance(value, float) else str(value))


WRITERS = {
    "colour": write_colour,
    "flag": write_flag,
    "choice": str,
    "number": write_number,
}


@dataclass(frozen=True)
class Setting:
    """One thing an effect can be told, and what kind of thing it is.

    The kind is here so the window can draw the right control -- a box to type
    in, a dropdown, a checkbox -- rather than a text field for everything and a
    user left to guess that "soft" wants the word "yes". The parser is the same
    either way, so a typed answer and a clicked one land in the same place.
    """

    label: str
    parse: object
    complaint: str
    kind: str = "number"
    options: tuple[str, ...] = ()
    #: What the window puts beside the control. The field name, unless that
    #: reads badly on its own -- "keep_clear" is a Python name, "keep clear"
    #: is a label.
    title: str = ""

    def write(self, value) -> str:
        """The value as it would be typed."""
        return WRITERS[self.kind](value)

    def shown(self) -> str:
        return self.title or self.label


# What each effect takes after its name, in order. One table rather than a
# branch per effect, so adding an effect is adding a row.
SETTINGS: dict[type[Effect], tuple[Setting, ...]] = {
    Transparent: (
        Setting(
            "colour", parse_colour,
            "A colour is a name like white or a hex value like #ffffff",
            kind="colour",
        ),
        Setting(
            "match", choice_of(Transparent.MATCHES),
            "Matching is tolerance or exact",
            kind="choice", options=Transparent.MATCHES,
        ),
        Setting(
            "tolerance", int,
            "A tolerance is a whole number of levels, 0 to 255",
        ),
        Setting(
            "soft", parse_flag,
            "Soft edges are yes or no",
            kind="flag",
        ),
    ),
    Blur: (
        Setting("radius", float, "A blur radius is a number of pixels"),
        Setting(
            "keep_clear", parse_flag,
            "Keeping the clear areas clear is yes or no",
            kind="flag", title="keep clear",
        ),
    ),
    Grayscale: (
        Setting(
            "tint", parse_colour,
            "A tint is a colour name like gray or a hex like #8a5a2b",
            kind="colour",
        ),
        Setting(
            "keep_clear", parse_flag,
            "Keeping the clear areas clear is yes or no",
            kind="flag", title="keep clear",
        ),
    ),
    Noise: (
        Setting("amount", int, "A noise amount is a whole number of grey levels"),
        Setting("seed", int, "A noise seed is a whole number"),
        Setting(
            "keep_clear", parse_flag,
            "Keeping the clear areas clear is yes or no",
            kind="flag", title="keep clear",
        ),
    ),
    Monochrome: (
        Setting("threshold", int, "A monochrome threshold is a whole number"),
        Setting(
            "keep_clear", parse_flag,
            "Keeping the clear areas clear is yes or no",
            kind="flag", title="keep clear",
        ),
    ),
}


def describe(effects: tuple[Effect, ...]) -> str:
    """The effects as a line of prose, in the order they will run."""
    ordered = order_effects(effects)
    if not ordered:
        return "no effects"
    return ", ".join(effect.described() for effect in ordered)
