"""Find chapter timestamps in a video description.

A chapter is a line with a timestamp at its start or its end, and a title, such as
`1:15 Carbonara`, `(01:02:03) - Dessert` or `#1 Peanut Stew 0:54`. YouTube's own rules
for turning these into chapters (the first must be 0:00, at least three, each at least
10 seconds long) are not applied here, so every timestamp a creator wrote is kept, even
ones YouTube ignores.
"""

import re
from dataclasses import dataclass

# An optional bracket, [h:]mm:ss, an optional bracket and separator, then the title.
# The title can't start with a separator or a space. Otherwise `0:00 -` would be a
# chapter titled "-".
_TIMESTAMP_FIRST = re.compile(
    r"""
    ^\s*[(\[]?
    (?:(?P<hours>\d{1,2}):)?
    (?P<minutes>\d{1,2}):(?P<seconds>\d{2})
    [)\]]?
    \s*(?:[-–—|:]\s*)?
    (?P<title>[^-–—|:\s].*)
    """,
    re.VERBOSE,
)

# The title, an optional separator, then [h:]mm:ss at the very end of the line.
# The title is lazy (`*?`), so it stops before the separator and spaces instead of
# swallowing them, and ends on a non-space so it can't be empty.
_TIMESTAMP_LAST = re.compile(
    r"""
    ^(?P<title>.*?\S)
    \s*(?:[-–—|:]\s*)?
    (?:(?P<hours>\d{1,2}):)?
    (?P<minutes>\d{1,2}):(?P<seconds>\d{2})
    \s*$
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Chapter:
    """A titled point in a video, `start_seconds` from the beginning."""

    start_seconds: int
    title: str


def parse_chapters(description: str) -> list[Chapter]:
    """Return the chapters in a description, in the order they appear."""
    chapters = []
    for line in description.splitlines():
        match = _TIMESTAMP_FIRST.match(line) or _TIMESTAMP_LAST.match(line)
        if match is None:
            continue
        hours = int(match["hours"] or 0)
        minutes = int(match["minutes"])
        seconds = int(match["seconds"])
        if minutes >= 60 or seconds >= 60:
            continue
        start = hours * 3600 + minutes * 60 + seconds
        chapters.append(Chapter(start, match["title"].rstrip()))
    return chapters
