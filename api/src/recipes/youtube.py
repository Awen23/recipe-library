"""A small client for the parts of the YouTube Data API v3 this project uses."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import batched
from typing import Any, Self

import httpx2

# `PT#H#M#S`, or `P#DT#H#M#S` for videos a day or longer. Parts that are zero are
# left out. See `contentDetails.duration` in
# https://developers.google.com/youtube/v3/docs/videos
_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(value: str) -> int:
    """Convert a YouTube duration such as `PT19M17S` to seconds."""
    match = _DURATION.match(value)
    if match is None:
        raise ValueError(f"Unrecognised duration: {value!r}")
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


@dataclass(frozen=True)
class Video:
    """The details of one video that this project keeps."""

    id: str
    title: str
    description: str
    duration_seconds: int
    published_at: str
    channel_id: str  # stays the same if the channel is renamed
    channel_title: str
    thumbnail_url: str
    embeddable: bool  # whether the creator lets other sites show it in an iframe

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
            channel_id=snippet["channelId"],
            channel_title=snippet["channelTitle"],
            # 320x180, the same shape as the video. Every video has this size.
            thumbnail_url=snippet["thumbnails"]["medium"]["url"],
            embeddable=item["status"]["embeddable"],
        )


@dataclass(frozen=True)
class Comment:
    """A top-level comment on a video."""

    id: str
    text: str
    published_at: str

    @classmethod
    def from_api(cls, thread: dict[str, Any]) -> Self:
        """Build a Comment from one item of a `commentThreads.list` response."""
        comment = thread["snippet"]["topLevelComment"]
        return cls(
            id=comment["id"],
            text=comment["snippet"]["textDisplay"],
            published_at=comment["snippet"]["publishedAt"],
        )


API_BASE_URL = "https://www.googleapis.com/youtube/v3"
PAGE_SIZE = 50  # the most items the API returns per request
COMMENTS_TO_CHECK = 20  # a creator's pinned or recipe comment is near the top


class YouTubeError(Exception):
    """The YouTube API returned an error."""


class QuotaExceededError(YouTubeError):
    """The API key has used up its daily quota."""


class CommentsDisabledError(YouTubeError):
    """The video has its comments turned off."""


class YouTubeClient:
    """Calls the YouTube Data API with an API key. Use it in a `with` block."""

    def __init__(
        self, api_key: str, *, transport: httpx2.BaseTransport | None = None
    ) -> None:
        # The key goes in a header, not the URL, so it never appears in logged URLs.
        self._http = httpx2.Client(
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
        """Return the ID of every video in the playlist, in playlist order."""
        params: dict[str, Any] = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": PAGE_SIZE,
        }
        page = self._get("playlistItems", params)
        video_ids = _video_ids_on(page)
        while "nextPageToken" in page:
            params["pageToken"] = page["nextPageToken"]
            page = self._get("playlistItems", params)
            video_ids.extend(_video_ids_on(page))
        return video_ids

    def videos(self, video_ids: Sequence[str]) -> list[Video]:
        """Fetch details for these videos.

        Deleted and private videos are left out by the API, so they're missing here.
        """
        videos: list[Video] = []
        for batch in batched(video_ids, PAGE_SIZE, strict=False):
            params = {"part": "snippet,contentDetails,status", "id": ",".join(batch)}
            page = self._get("videos", params)
            videos.extend(Video.from_api(item) for item in page["items"])
        return videos

    def creator_comments(self, video_id: str) -> list[Comment]:
        """The comments by the video's own channel, among its top comments.

        Returns none if the video has its comments turned off.
        """
        params: dict[str, Any] = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": COMMENTS_TO_CHECK,
            "order": "relevance",
            "textFormat": "plainText",
        }
        try:
            page = self._get("commentThreads", params)
        except CommentsDisabledError:
            return []
        return [
            Comment.from_api(thread)
            for thread in page["items"]
            if _is_by_creator(thread)
        ]

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._http.get(endpoint, params=params)
        if response.is_error:
            raise _error_from(response)
        body: dict[str, Any] = response.json()
        return body


def _video_ids_on(page: dict[str, Any]) -> list[str]:
    """The video IDs on one page of a `playlistItems` response."""
    return [item["contentDetails"]["videoId"] for item in page["items"]]


def _is_by_creator(thread: dict[str, Any]) -> bool:
    """Whether one item of a `commentThreads` response was posted by the video's
    own channel."""
    return (
        thread["snippet"]["channelId"]
        == thread["snippet"]["topLevelComment"]["snippet"]["authorChannelId"]["value"]
    )


def _error_from(response: httpx2.Response) -> YouTubeError:
    """Turn an error response into an exception with YouTube's message."""
    error = response.json()["error"]
    reasons = {detail["reason"] for detail in error["errors"]}
    if "quotaExceeded" in reasons:
        return QuotaExceededError(
            "The YouTube API daily quota is used up. "
            "It resets at midnight Pacific time."
        )
    if "commentsDisabled" in reasons:
        return CommentsDisabledError("This video has its comments turned off.")
    return YouTubeError(
        f"YouTube API error (HTTP {response.status_code}): {error['message']}"
    )
