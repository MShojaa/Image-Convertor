#!/usr/bin/env python3
"""Read or move `__version__` in image_convertor/__init__.py.

Split out of merge.bat rather than done in batch, because replacing one line
of a file in cmd means shelling out to PowerShell anyway, and this repo
already needs Python to run its tests.

`__version__` is the only place the number is written -- `--version` on the
command line reads it from there -- so this touches exactly one line.

    python scripts/bump_version.py --show
    python scripts/bump_version.py --next minor      # prints the next number
    python scripts/bump_version.py --set 1.2.0       # writes it
"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INIT = os.path.join(os.path.dirname(HERE), 'image_convertor', '__init__.py')
# Anchored on the closing quote, NOT on end-of-line. `$` under re.M matches
# before the \n but AFTER the \r, so a CRLF file -- which git leaves in the
# working tree here -- would never match a line plainly sitting there. Ending
# at the quote also means the replacement cannot touch the line ending.
PATTERN = re.compile(r'^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"', re.M)


def current():
    text = io.open(INIT, encoding='utf-8', newline='').read()
    found = PATTERN.search(text)
    if not found:
        raise SystemExit("__version__ not found in %s -- has its shape changed?" % INIT)
    return found.group(1)


def bumped(version, part):
    major, minor, patch = (int(n) for n in version.split('.'))
    if part == 'major':
        return '%d.0.0' % (major + 1)
    if part == 'minor':
        return '%d.%d.0' % (major, minor + 1)
    if part == 'patch':
        return '%d.%d.%d' % (major, minor, patch + 1)
    raise SystemExit('unknown part: %s' % part)


def write(version):
    if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+$', version):
        raise SystemExit('not a version: %s' % version)
    text = io.open(INIT, encoding='utf-8', newline='').read()
    new, count = PATTERN.subn('__version__ = "%s"' % version, text)
    if count != 1:
        raise SystemExit('expected one __version__ line, found %d' % count)
    io.open(INIT, 'w', encoding='utf-8', newline='').write(new)
    return version


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--show', action='store_true', help='print the current version')
    group.add_argument('--next', choices=('major', 'minor', 'patch'),
                       help='print what that bump would give, without writing')
    group.add_argument('--set', metavar='X.Y.Z', help='write this version')
    args = parser.parse_args(argv)

    if args.show:
        print(current())
    elif args.next:
        print(bumped(current(), args.next))
    else:
        print(write(args.set))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
