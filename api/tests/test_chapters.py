import pytest

from recipes.chapters import Chapter, parse_chapters

from fakes import read_fixture

# Lines copied from real descriptions in the playlist.
TIMESTAMP_FIRST = [
    pytest.param("00:00 - Intro", [Chapter(0, "Intro")], id="dash"),
    pytest.param("0:00 Intro ", [Chapter(0, "Intro")], id="trailing space"),
    pytest.param(
        "05:26- Crispy Polenta ", [Chapter(326, "Crispy Polenta")], id="dash, no space"
    ),
    pytest.param(
        "14:58 -  Stuffed Polenta", [Chapter(898, "Stuffed Polenta")], id="double space"
    ),
    pytest.param(
        "19:03 Snack #8- Chickpea Avocado Mash on Rice Cake",
        [Chapter(1143, "Snack #8- Chickpea Avocado Mash on Rice Cake")],
        id="dash inside title",
    ),
    pytest.param(
        "05:42 Using flavor bombs in Indian meals 🇮🇳",
        [Chapter(342, "Using flavor bombs in Indian meals 🇮🇳")],
        id="emoji",
    ),
    pytest.param("0:00 先頭", [Chapter(0, "先頭")], id="japanese"),
    pytest.param(
        "2:35 DIVIDE INTO 4", [Chapter(155, "DIVIDE INTO 4")], id="step, not recipe"
    ),
]

NO_CHAPTER = [
    pytest.param(
        "Full Recipe + Nutritional Info: https://goodfoodbaddie.com/blueberry-baked-oatmeal/",
        [],
        id="link",
    ),
    pytest.param("- 1 + 1/2 cups oats", [], id="ingredient"),
]

# Not from the data: these pin down the rules for what counts as a timestamp.
RULES = [
    pytest.param("1:02:03 Dessert", [Chapter(3723, "Dessert")], id="with hours"),
    pytest.param("Skip to 1:15 for the sauce", [], id="timestamp mid-line"),
    pytest.param("1:15", [], id="no title"),
    pytest.param("0:00 -", [], id="separator but no title"),
    pytest.param("1:75 Oops", [], id="seconds over 59"),
    pytest.param("1:60:00 Oops", [], id="minutes over 59"),
]


@pytest.mark.parametrize(("line", "expected"), TIMESTAMP_FIRST + NO_CHAPTER + RULES)
def test_parse_chapters_line(line: str, expected: list[Chapter]) -> None:
    assert parse_chapters(line) == expected


def test_parse_chapters_in_a_whole_description() -> None:
    description = read_fixture("descriptions.json")["whr7iOKRXTA"]

    assert parse_chapters(description) == [
        Chapter(0, "Intro"),
        Chapter(102, "Breakfasts"),
        Chapter(561, "Mexican inspired salad"),
        Chapter(685, "Sticky lemon & garlic tofu"),
        Chapter(857, "Hearty vegan lasagne"),
        Chapter(1011, "Raspberry oat bars"),
    ]


def test_a_short_without_timestamps_has_no_chapters() -> None:
    description = read_fixture("descriptions.json")["gOxwhuntyMY"]

    assert parse_chapters(description) == []
