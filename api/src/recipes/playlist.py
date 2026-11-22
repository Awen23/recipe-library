"""Fetch a whole playlist: every available video, in playlist order."""

from collections.abc import Mapping
from dataclasses import dataclass

from recipes.youtube import Comment, Video, YouTubeClient


@dataclass(frozen=True)
class Playlist:
    """The available videos in a playlist."""

    id: str
    videos: tuple[Video, ...]
    unavailable_count: int  # deleted or private videos, which the API won't describe
    # The comments each video's own channel left on it, keyed by video ID.
    creator_comments: Mapping[str, tuple[Comment, ...]]


def fetch_playlist(client: YouTubeClient, playlist_id: str) -> Playlist:
    """Fetch every available video in the playlist, in playlist order, with the
    comments its creator left on it."""
    video_ids = client.playlist_video_ids(playlist_id)
    videos = tuple(client.videos(video_ids))
    creator_comments = {
        video.id: tuple(client.creator_comments(video.id)) for video in videos
    }
    return Playlist(
        playlist_id,
        videos,
        unavailable_count=len(video_ids) - len(videos),
        creator_comments=creator_comments,
    )
