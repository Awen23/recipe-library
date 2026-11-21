"""Find chapter timestamps in a video description.

A chapter is a line that starts with a timestamp and has a title, such as
`1:15 Carbonara` or `(01:02:03) - Dessert`. YouTube's own rules for turning these into
chapters (the first must be 0:00, at least three, each at least 10 seconds long) are not
applied here, so every timestamp a creator wrote is kept, even ones YouTube ignores.
"""

import re
from dataclasses import dataclass

# An optional bracket, [h:]mm:ss, an optional bracket and separator, then the title.
# The title can't start with a separator or a space. Otherwise `0:00 -` would be a
# chapter titled "-".
_CHAPTER_LINE = re.compile(
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


@dataclass(frozen=True)
class Chapter:
    """A titled point in a video, `start_seconds` from the beginning."""

    start_seconds: int
    title: str


def parse_chapters(description: str) -> list[Chapter]:
    """Return the chapters in a description, in the order they appear."""
    chapters = []
    for line in description.splitlines():
        match = _CHAPTER_LINE.match(line)
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
