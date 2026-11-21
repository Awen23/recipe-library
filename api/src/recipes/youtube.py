"""A small client for the parts of the YouTube Data API v3 this project uses."""

import re
from dataclasses import dataclass
from typing import Any, Self

import httpx

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


API_BASE_URL = "https://www.googleapis.com/youtube/v3"
PAGE_SIZE = 50  # the most items the API returns per request


class YouTubeError(Exception):
    """The YouTube API returned an error."""


class QuotaExceededError(YouTubeError):
    """The API key has used up its daily quota."""


class YouTubeClient:
    """Calls the YouTube Data API with an API key. Use it in a `with` block."""

    def __init__(
        self, api_key: str, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        # The key goes in a header, not the URL, so it never appears in logged URLs.
        self._http = httpx.Client(
            base_url=API_BASE_URL,
            headers={"X-Goog-Api-Key": api_key},
            timeout=30,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._http.close()

    def playlist_video_ids(self, playlist_id: str) -> list[str]:
        """Return the IDs of the videos on the first page of the playlist."""
        params: dict[str, Any] = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": PAGE_SIZE,
        }
        page = self._get("playlistItems", params)
        return [item["contentDetails"]["videoId"] for item in page["items"]]

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._http.get(endpoint, params=params)
        if response.is_error:
            raise _error_from(response)
        body: dict[str, Any] = response.json()
        return body


def _error_from(response: httpx.Response) -> YouTubeError:
    """Turn an error response into an exception with YouTube's message."""
    error = response.json()["error"]
    reasons = {detail["reason"] for detail in error["errors"]}
    if "quotaExceeded" in reasons:
        return QuotaExceededError(
            "The YouTube API daily quota is used up. "
            "It resets at midnight Pacific time."
        )
    return YouTubeError(
        f"YouTube API error (HTTP {response.status_code}): {error['message']}"
    )
