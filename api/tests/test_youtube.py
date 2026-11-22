import httpx2
import pytest

from recipes.youtube import (
    PAGE_SIZE,
    Comment,
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
        channel_id="UC1F8Add7s3dEDmweoWLJkdg",
        channel_title="Capri Lilly",
        thumbnail_url="https://i.ytimg.com/vi/gOxwhuntyMY/mqdefault.jpg",
        embeddable=True,
    )


def test_video_from_api_knows_when_embedding_is_turned_off() -> None:
    [item] = [
        item
        for item in read_fixture("videos.json")["items"]
        if item["id"] == "eG0tXlljTtI"
    ]

    assert Video.from_api(item).embeddable is False


def test_playlist_video_ids_asks_for_the_playlist(fake_api: FakeYouTubeApi) -> None:
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        client.playlist_video_ids("PLAYLIST_ID")

    # The fake answers the same whatever we send, so check what we asked for here.
    first_request = fake_api.requests[0]
    assert first_request.url.path.endswith("/playlistItems")
    assert first_request.url.params["playlistId"] == "PLAYLIST_ID"
    assert first_request.url.params["part"] == "contentDetails"


def test_playlist_video_ids_follows_next_page_token(fake_api: FakeYouTubeApi) -> None:
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        video_ids = client.playlist_video_ids("PLAYLIST_ID")

    # Both pages, in order. Deleted and private videos are still listed: the playlist
    # keeps an entry for them.
    assert video_ids == [
        "whr7iOKRXTA",
        "nHr9LqK3PKc",
        "Iop_LKTis_U",  # deleted
        "eG0tXlljTtI",
        "gOxwhuntyMY",
        "H0tkAEL6CS8",
        "d9yFMrsKQWk",  # private
    ]
    # The second request carried page 1's token, and there was no third.
    page_two_token = read_fixture("playlist_items_page_1.json")["nextPageToken"]
    page_tokens = [request.url.params.get("pageToken") for request in fake_api.requests]
    assert page_tokens == [None, page_two_token]


def test_api_key_is_sent_in_a_header_not_the_url(fake_api: FakeYouTubeApi) -> None:
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        client.playlist_video_ids("PLAYLIST_ID")

    for request in fake_api.requests:
        assert request.headers["X-Goog-Api-Key"] == "test-key"
        assert "test-key" not in str(request.url)


def test_exhausted_quota_raises_quota_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(403, json=read_fixture("error_quota_exceeded.json"))

    with (
        YouTubeClient("test-key", transport=httpx2.MockTransport(handler)) as client,
        pytest.raises(QuotaExceededError),
    ):
        client.playlist_video_ids("PLAYLIST_ID")


def test_other_api_errors_include_youtubes_message() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json=read_fixture("error_playlist_not_found.json"))

    with (
        YouTubeClient("test-key", transport=httpx2.MockTransport(handler)) as client,
        pytest.raises(YouTubeError, match="HTTP 404.*cannot be found"),
    ):
        client.playlist_video_ids("NOT_A_PLAYLIST")


def test_videos_returns_only_what_the_api_describes(fake_api: FakeYouTubeApi) -> None:
    page_one_ids = ["whr7iOKRXTA", "nHr9LqK3PKc", "Iop_LKTis_U"]
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        videos = client.videos(page_one_ids)

    # Our part: every listed ID is asked for, including the deleted one.
    [videos_request] = fake_api.requests
    assert videos_request.url.params["id"] == "whr7iOKRXTA,nHr9LqK3PKc,Iop_LKTis_U"
    assert videos_request.url.params["part"] == "snippet,contentDetails,status"
    # The API's part: the deleted Iop_LKTis_U has no details, so no Video for it.
    assert [video.id for video in videos] == ["whr7iOKRXTA", "nHr9LqK3PKc"]


def test_videos_batches_ids_in_groups_of_50() -> None:
    requested_batches: list[list[str]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested_batches.append(request.url.params["id"].split(","))
        return httpx2.Response(200, json={"items": []})

    video_ids = [f"video{number:06}" for number in range(120)]  # not real IDs
    with YouTubeClient("test-key", transport=httpx2.MockTransport(handler)) as client:
        client.videos(video_ids)

    assert [len(batch) for batch in requested_batches] == [PAGE_SIZE, PAGE_SIZE, 20]


def test_creator_comments_keeps_only_the_videos_own_channel(
    fake_api: FakeYouTubeApi,
) -> None:
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        comments = client.creator_comments("eG0tXlljTtI")

    # Of the three comments, only the first is by the channel that posted the video.
    assert comments == [
        Comment(
            id="Ugwnsgb1qinFFq2Wf3B4AaABAg",
            text=(
                "I feel guilty of using a lot of plastic wrap to make these... But I "
                "haven't thought of a good substitute. If you have a good idea, "
                "please share in the comment!"
            ),
            published_at="2022-08-28T07:08:42Z",
        )
    ]


def test_creator_comments_asks_for_the_top_comments_as_plain_text(
    fake_api: FakeYouTubeApi,
) -> None:
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        client.creator_comments("eG0tXlljTtI")

    [request] = fake_api.requests
    assert request.url.path.endswith("/commentThreads")
    assert request.url.params["videoId"] == "eG0tXlljTtI"
    assert request.url.params["order"] == "relevance"
    assert request.url.params["maxResults"] == "20"
    # Without this, the text comes back as HTML, with `<br>` and escaped characters.
    assert request.url.params["textFormat"] == "plainText"


def test_creator_comments_is_empty_when_comments_are_turned_off() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(403, json=read_fixture("error_comments_disabled.json"))

    with YouTubeClient("test-key", transport=httpx2.MockTransport(handler)) as client:
        assert client.creator_comments("eG0tXlljTtI") == []
