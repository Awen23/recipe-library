"""Fetch a whole playlist: every available video, in playlist order."""

from dataclasses import dataclass

from recipes.youtube import Video, YouTubeClient


@dataclass(frozen=True)
class Playlist:
    """The available videos in a playlist."""

    id: str
    videos: tuple[Video, ...]
    unavailable_count: int  # deleted or private videos, which the API won't describe


def fetch_playlist(client: YouTubeClient, playlist_id: str) -> Playlist:
    """Fetch every available video in the playlist, in playlist order."""
    video_ids = client.playlist_video_ids(playlist_id)
    videos = tuple(client.videos(video_ids))
    return Playlist(playlist_id, videos, unavailable_count=len(video_ids) - len(videos))
