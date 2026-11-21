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

# 22 videos put the timestamp at the end of the line instead.
TIMESTAMP_LAST = [
    pytest.param("intro 0:00", [Chapter(0, "intro")], id="last: plain"),
    pytest.param("intro: 0:00", [Chapter(0, "intro")], id="last: colon before"),
    pytest.param(
        "#1 Peanut Sweet Potato Stew 0:54",
        [Chapter(54, "#1 Peanut Sweet Potato Stew")],
        id="last: numbered recipe",
    ),
    pytest.param(
        "#4 No Bake Cinnamon Raisin Bars  6:04",
        [Chapter(364, "#4 No Bake Cinnamon Raisin Bars")],
        id="last: double space",
    ),
    pytest.param(
        "#2.5 BEST Iced Chai Latte 3:35 ",
        [Chapter(215, "#2.5 BEST Iced Chai Latte")],
        id="last: trailing space",
    ),
    pytest.param(
        "#3 Green Pasta 💚 4:05", [Chapter(245, "#3 Green Pasta 💚")], id="last: emoji"
    ),
    pytest.param(
        "how to iron (plantbased) 0:54",
        [Chapter(54, "how to iron (plantbased)")],
        id="last: bracket before",
    ),
    pytest.param(
        "Japan vlog / E Sim Discount 3:38 ",
        [Chapter(218, "Japan vlog / E Sim Discount")],
        id="last: not a recipe",
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


@pytest.mark.parametrize(
    ("line", "expected"), TIMESTAMP_FIRST + TIMESTAMP_LAST + NO_CHAPTER + RULES
)
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


def test_parse_chapters_in_a_whole_description_with_timestamps_last() -> None:
    description = read_fixture("descriptions.json")["nHr9LqK3PKc"]

    assert parse_chapters(description) == [
        Chapter(0, "intro"),
        Chapter(54, "#1 Peanut Sweet Potato Stew"),
        Chapter(177, "#2 Tofu Burger Patties"),
        Chapter(256, "#3 Berry Breakfast Crumble Bars"),
        Chapter(400, "#4 Tofu Enchiladas"),
        Chapter(661, "#5 Whipped Bean Cookie Dough"),
        Chapter(767, "#6 Two Overnight Focaccias"),
    ]


def test_a_short_without_timestamps_has_no_chapters() -> None:
    description = read_fixture("descriptions.json")["gOxwhuntyMY"]

    assert parse_chapters(description) == []
