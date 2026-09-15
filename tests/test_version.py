"""The version number, checked by shape rather than by value.

`scripts/bump_version.py` rewrites `__version__` at every merge, so anything
here that named a number would have to be edited by the same script -- and a
test the release process has to keep in step is a test that eventually stops
being run. These assert the things that stay true across every bump.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

import image_convertor
from image_convertor import cli

ROOT = Path(__file__).resolve().parent.parent
BUMP = ROOT / "scripts" / "bump_version.py"


def test_the_version_is_three_dotted_numbers():
    assert re.fullmatch(r"\d+\.\d+\.\d+", image_convertor.__version__)


def test_the_version_flag_prints_that_same_number(capsys):
    """--version reads __version__; nothing else may define the number."""
    with pytest.raises(SystemExit) as exited:
        cli.main(["--version"])

    assert exited.value.code == 0
    assert capsys.readouterr().out.strip() == image_convertor.__version__


def bump(*args):
    """Run bump_version.py the way merge.bat does, and return what it printed."""
    result = subprocess.run(
        [sys.executable, str(BUMP), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_bump_version_reads_the_same_number():
    """The release script and the package must not disagree about the version."""
    assert bump("--show") == image_convertor.__version__


@pytest.mark.parametrize(
    "part, expected",
    [("major", "2.0.0"), ("minor", "1.4.0"), ("patch", "1.3.8")],
)
def test_bump_version_moves_the_right_number(part, expected, monkeypatch):
    """--next is pure arithmetic, so it can be checked on a made-up version."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("bump_version", BUMP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.bumped("1.3.7", part) == expected


def test_bump_version_does_not_write_when_only_asked():
    """--show and --next must leave the file alone; merge.bat calls them first."""
    before = (ROOT / "image_convertor" / "__init__.py").read_bytes()

    bump("--show")
    bump("--next", "minor")

    assert (ROOT / "image_convertor" / "__init__.py").read_bytes() == before
