import httpx
import pytest

from recipes.youtube import (
    QuotaExceededError,
    Video,
    YouTubeClient,
    YouTubeError,
    parse_duration,
)

from fakes import FakeYouTubeApi, read_fixture


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        # The three shapes in the real playlist.
        ("PT25S", 25),
        ("PT1M", 60),
        ("PT19M17S", 1157),
    ],
)
def test_parse_duration(duration: str, expected: int) -> None:
    assert parse_duration(duration) == expected


def test_parse_duration_rejects_other_formats() -> None:
    with pytest.raises(ValueError, match="19:17"):
        parse_duration("19:17")


def test_video_from_api_maps_youtube_fields_to_ours() -> None:
    [item] = [
        item
        for item in read_fixture("videos.json")["items"]
        if item["id"] == "gOxwhuntyMY"
    ]

    assert Video.from_api(item) == Video(
        id="gOxwhuntyMY",
        title="Blueberry Baked Oatmeal (Vegan and Gluten-Free) #shorts",
        description=(
            "Blueberry Baked Oatmeal is perfect for an easy meal prep breakfast. "
            "Combine all the ingredients in one dish, bake, and enjoy throughout the "
            "week! This recipe is vegan, gluten-free, naturally sweetened, and super "
            "easy to make!\n\nFull Recipe + Nutritional Info: "
            "https://goodfoodbaddie.com/blueberry-baked-oatmeal/"
        ),
        duration_seconds=25,
        published_at="2022-03-16T22:36:39Z",
        channel_title="Capri Lilly",
    )


def test_playlist_video_ids_reads_a_page(fake_api: FakeYouTubeApi) -> None:
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        video_ids = client.playlist_video_ids("PLAYLIST_ID")

    # The deleted video is still listed: the playlist keeps an entry for it.
    assert video_ids == ["whr7iOKRXTA", "nHr9LqK3PKc", "Iop_LKTis_U"]


def test_api_key_is_sent_in_a_header_not_the_url(fake_api: FakeYouTubeApi) -> None:
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        client.playlist_video_ids("PLAYLIST_ID")

    [request] = fake_api.requests
    assert request.headers["X-Goog-Api-Key"] == "test-key"
    assert "test-key" not in str(request.url)


def test_exhausted_quota_raises_quota_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json=read_fixture("error_quota_exceeded.json"))

    with (
        YouTubeClient("test-key", transport=httpx.MockTransport(handler)) as client,
        pytest.raises(QuotaExceededError),
    ):
        client.playlist_video_ids("PLAYLIST_ID")


def test_other_api_errors_include_youtubes_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json=read_fixture("error_playlist_not_found.json"))

    with (
        YouTubeClient("test-key", transport=httpx.MockTransport(handler)) as client,
        pytest.raises(YouTubeError, match="HTTP 404.*cannot be found"),
    ):
        client.playlist_video_ids("NOT_A_PLAYLIST")
