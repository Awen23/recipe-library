"""A small client for the parts of the YouTube Data API v3 this project uses."""

import re
from dataclasses import dataclass
from typing import Any, Self

_DURATION = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def parse_duration(value: str) -> int:
    """Convert a YouTube duration such as `PT19M17S` to seconds."""
    match = _DURATION.match(value)
    if match is None:
        raise ValueError(f"Unrecognised duration: {value!r}")
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


@dataclass(frozen=True)
class Video:
    """The details of one video that this project keeps."""

    id: str
    title: str
    description: str
    duration_seconds: int
    published_at: str
    channel_title: str

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> Self:
        """Build a Video from one item of a `videos.list` response."""
        snippet = item["snippet"]
        return cls(
            id=item["id"],
            title=snippet["title"],
            description=snippet["description"],
            duration_seconds=parse_duration(item["contentDetails"]["duration"]),
            published_at=snippet["publishedAt"],
            channel_title=snippet["channelTitle"],
        )
