"""What the app remembers between runs.

One JSON file in the user's profile -- `%LOCALAPPDATA%\\Image-Convertor\\
settings.json` on Windows -- rather than beside the executable. Beside the exe
would be the more portable choice and was the other candidate; the profile won
because the install folder is not reliably writable (Program Files is not) and
because a rebuilt or moved exe would otherwise lose everything the user had
set.

Every read is defensive, and that is the whole design. A settings file is the
one input the app cannot validate at the source: it can be hand-edited, left
half-written by a machine that lost power, or arrive from a newer version that
knows keys this one does not. So a bad file is never an error the user sees --
it falls back to the defaults, exactly as if the file were not there. Nothing
here is worth interrupting someone over; it is a convenience, and a convenience
that refuses to start is worse than no convenience.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

APP_FOLDER = "Image-Convertor"
FILENAME = "settings.json"


@dataclass(frozen=True)
class Settings:
    """Everything remembered, with the value used when it is not.

    A field here is a field in the file. Adding one needs no migration: an
    older file simply does not carry it, and `load` fills the default in --
    which is the same path a corrupt file takes.
    """

    #: The last folder images were read from, when it was not the one beside
    #: the app. Empty means "no memory of one".
    input_folder: str = ""

    #: Where the results were written, when it was not the folder beside the
    #: app. Empty means that default, the same as for the input.
    output_folder: str = ""

    #: The last size box, as typed ("128x64"). Empty means no resizing.
    size: str = ""

    #: The last --format, by name. Empty means "the same as the input".
    output_format: str = ""

    #: The last effects, as they would be typed on the command line.
    effects: tuple[str, ...] = ()

    #: "system", "dark" or "light". "system" follows the OS setting, which
    #: is the default because an app that ignores it is the odd one out --
    #: but a deliberate choice has to stick, which is why this is three
    #: values and not a boolean.
    theme: str = "system"


def folder() -> Path:
    """Where the settings file lives.

    `%LOCALAPPDATA%` on Windows, `$XDG_CONFIG_HOME` or `~/.config` elsewhere.
    Local rather than roaming: it is a convenience tied to this machine, and a
    remembered folder path on one machine is often wrong on another.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / APP_FOLDER


def path() -> Path:
    return folder() / FILENAME


def load() -> Settings:
    """The stored settings, or the defaults for anything missing or wrong.

    Never raises. A file that cannot be read, cannot be parsed, or holds
    something other than an object is the same as no file at all.
    """
    try:
        text = path().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return Settings()

    try:
        stored = json.loads(text)
    except json.JSONDecodeError:
        return Settings()

    if not isinstance(stored, dict):
        return Settings()

    return _from(stored)


def _from(stored: dict) -> Settings:
    """Build Settings from whatever was in the file, field by field.

    Per field, not in one go: one key of the wrong type should cost that key
    and nothing else. A file written by a later version carrying keys this one
    has never heard of is not an error either -- they are ignored, and `save`
    below is what actually loses them.
    """
    known = {field.name: field for field in fields(Settings)}
    values = {}

    for name, field in known.items():
        if name not in stored:
            continue
        value = stored[name]

        if name == "effects":
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                values[name] = tuple(value)
            continue

        if isinstance(value, str):
            values[name] = value

    return Settings(**values)


def save(settings: Settings) -> bool:
    """Write the settings. Says whether it worked; never raises.

    The folder may not exist, the disk may be full, the profile may be on a
    share that has gone away. None of that is worth stopping a conversion that
    has already happened, so the caller gets a bool it is free to ignore.
    """
    try:
        folder().mkdir(parents=True, exist_ok=True)
        path().write_text(
            json.dumps(asdict(settings), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def remember(**changes: object) -> Settings:
    """Load, change some fields, save. The way callers write one setting."""
    updated = replace(load(), **changes)
    save(updated)
    return updated
