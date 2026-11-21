import pytest

from recipes.youtube import Video, parse_duration

from fakes import read_fixture


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
