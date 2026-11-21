from recipes.playlist import fetch_playlist
from recipes.youtube import YouTubeClient

from fakes import FakeYouTubeApi


def test_fetch_playlist_skips_and_counts_unavailable_videos(
    fake_api: FakeYouTubeApi,
) -> None:
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        playlist = fetch_playlist(client, "PLAYLIST_ID")

    # Seven videos are listed. The deleted Iop_LKTis_U and the private d9yFMrsKQWk
    # have no details, so they're left out and counted instead.
    assert [video.id for video in playlist.videos] == [
        "whr7iOKRXTA",
        "nHr9LqK3PKc",
        "eG0tXlljTtI",
        "gOxwhuntyMY",
        "H0tkAEL6CS8",
    ]
    assert playlist.unavailable_count == 2


def test_fetch_playlist_uses_the_playlist_id_it_was_given(
    fake_api: FakeYouTubeApi,
) -> None:
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        playlist = fetch_playlist(client, "PLAYLIST_ID")

    # The fake answers the same for any playlist, so check the ID was passed on.
    assert fake_api.requests[0].url.params["playlistId"] == "PLAYLIST_ID"
    assert playlist.id == "PLAYLIST_ID"
