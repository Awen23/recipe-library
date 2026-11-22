from dataclasses import replace
from typing import Any

import httpx2
import pytest
from sqlalchemy import Engine, select, update

from recipes.ai import AILine, Claude
from recipes.building import build_recipes, fill_details
from recipes.details import copied_lines, from_answer, plain_details, readable_pages
from recipes.fetching import fetch_linked_pages
from recipes.models import Details, Line, StoredPage
from recipes.pages import NO_RECIPE
from recipes.storage import recipes, videos_to_fill

from fakes import FakeClaudeApi, read_fixture, recipe_web, recorded_details

OATMEAL_ID = "gOxwhuntyMY"  # one recipe, with a link to its page
SIX_MEALS_ID = "nHr9LqK3PKc"  # six recipes: one on a linked page, five in the text
SEITAN_ID = "eG0tXlljTtI"  # its description is trimmed, so it has nothing to read


def copied(lines: list[str]) -> list[AILine]:
    """Lines as Claude copies them: none of them notes."""
    return [AILine(text=line, note=False) for line in lines]


def texts(lines: list[Line]) -> list[str]:
    return [line.text for line in lines]


@pytest.fixture
def fake_claude() -> FakeClaudeApi:
    return FakeClaudeApi()


@pytest.fixture
def built(fetched: Engine, fake_claude: FakeClaudeApi) -> Engine:
    """The fixture videos split into recipes, with their links fetched from a web
    that has only the three recipe pages."""
    web = recipe_web()
    with web.fetcher() as fetcher:
        fetch_linked_pages(fetched, fetcher)
    with Claude("test-key", transport=fake_claude.transport) as claude:
        build_recipes(fetched, claude)
    return fetched


def fill(engine: Engine, fake_claude: FakeClaudeApi) -> dict[str, str]:
    with Claude("test-key", transport=fake_claude.transport) as claude:
        return fill_details(engine, claude)


def details(engine: Engine, video_id: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        query = (
            select(recipes)
            .where(recipes.c.video_id == video_id)
            .order_by(recipes.c.position)
        )
        return [row._asdict() for row in connection.execute(query)]


def test_plain_code_settles_a_one_recipe_video_with_a_recipe_page(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    fill(built, fake_claude)

    [oatmeal] = details(built, OATMEAL_ID)
    assert (oatmeal["source"], oatmeal["details_by"]) == ("link", "code")
    assert (
        oatmeal["source_url"] == "https://goodfoodbaddie.com/blueberry-baked-oatmeal/"
    )
    assert oatmeal["ingredients"][0]["text"] == (
        "2 1/2 cups Rolled Oats (ensure gluten-free if necessary)"
    )


def test_claude_is_asked_only_about_videos_plain_code_cant_settle(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    before = len(fake_claude.requests)

    failed = fill(built, fake_claude)

    # The meal prep and six-meal videos. The oatmeal and brownies have one recipe
    # and a recipe page, and the seitan video has nothing to read.
    assert failed == {}
    assert len(fake_claude.requests) - before == 2


def test_claude_picks_a_page_for_one_recipe_and_the_text_for_the_others(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    fill(built, fake_claude)

    stew, patties, *_ = details(built, SIX_MEALS_ID)
    assert (stew["source"], stew["details_by"]) == ("link", "ai")
    # The page's own ingredients, not ones Claude wrote out.
    assert len(stew["ingredients"]) == 24
    assert (patties["source"], patties["source_url"]) == ("description", None)
    assert patties["ingredients"][0] == {"text": "400g firm tofu (14oz)", "note": False}


def test_a_video_with_nothing_to_read_is_marked_as_looked_at(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    fill(built, fake_claude)

    [seitan] = details(built, SEITAN_ID)
    assert (seitan["details_by"], seitan["source"], seitan["ingredients"]) == (
        "code",
        None,
        None,
    )


def test_looking_again_asks_nothing_and_changes_nothing(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    fill(built, fake_claude)
    with built.begin() as connection:  # as if corrected by hand
        connection.execute(
            update(recipes)
            .where(recipes.c.video_id == OATMEAL_ID)
            .values(ingredients=["3 cups oats"], details_by="hand")
        )
    before = len(fake_claude.requests)

    fill(built, fake_claude)
    assert len(fake_claude.requests) == before
    assert details(built, OATMEAL_ID)[0]["ingredients"] == ["3 cups oats"]


def test_a_video_claude_couldnt_answer_about_is_left_for_the_next_build(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    """Not from the data: the error follows the shape in Anthropic's error docs."""
    error = {"type": "error", "error": {"type": "overloaded_error", "message": "x"}}
    fake_claude.queue.append(httpx2.Response(400, json=error))

    failed = fill(built, fake_claude)

    assert len(failed) == 1
    before = len(fake_claude.requests)
    fill(built, fake_claude)
    assert len(fake_claude.requests) - before == 1


def test_videos_wait_until_their_links_are_fetched(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    with Claude("test-key", transport=fake_claude.transport) as claude:
        build_recipes(fetched, claude)

    fill(fetched, fake_claude)  # before `recipes fetch` has fetched any links

    # Only the seitan video has no links to fetch, so only it was looked at.
    looked_at = {v.id for v in videos_to_fill(fetched)}
    assert SEITAN_ID not in looked_at
    assert len(looked_at) == 4


def test_copied_lines_keeps_only_lines_in_the_text() -> None:
    description = read_fixture("descriptions.json")[SIX_MEALS_ID]
    lines = [
        "400g firm tofu (14oz)",
        "1  medium sized onion,   minced",  # spaced differently
        "2 cups vegan mayo",  # Not from the data: a line that isn't written there
    ]

    assert texts(copied_lines(copied(lines), description)) == lines[:2]


def test_copied_lines_must_be_whole_lines() -> None:
    description = read_fixture("descriptions.json")[SIX_MEALS_ID]
    # Parts of the real lines "400g firm tofu (14oz)" and "1 tbsp yellow mustard".
    parts = ["firm tofu", "1 tbsp yellow"]

    assert copied_lines(copied(parts), description) == []


def test_copied_lines_may_leave_out_bullets() -> None:
    description = read_fixture("descriptions.json")["whr7iOKRXTA"]

    # Written there as "- 1/2 cup chia seeds".
    found = copied_lines(copied(["1/2 cup chia seeds"]), description)
    assert texts(found) == ["1/2 cup chia seeds"]


def test_chapter_timestamps_are_not_ingredient_lines(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    """Not from the data: a description that's only chapters, and no links."""
    [video] = [v for v in videos_to_fill(built) if v.id == SEITAN_ID]
    text = replace(video.text, description="0:00 Intro\n1:23 Pasta\n4:56 Soup")

    assert plain_details(replace(video, text=text)) == {
        recipe.id: Details(by="code") for recipe in video.recipes
    }


def test_a_refusal_marks_every_recipe_as_looked_at(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    """Not from the data: a refusal follows the shape in Anthropic's docs."""
    refusal: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [],
        "stop_reason": "refusal",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 0},
    }
    fake_claude.queue.append(httpx2.Response(200, json=refusal))

    failed = fill(built, fake_claude)

    assert failed == {}
    looked_at = [r for v in (SIX_MEALS_ID, "whr7iOKRXTA") for r in details(built, v)]
    # The first video asked about was refused, so its recipes have nothing.
    assert any(r["details_by"] == "ai" and r["source"] is None for r in looked_at)


def test_an_answer_with_recipe_numbers_it_was_not_shown_finds_nothing(
    built: Engine,
) -> None:
    """Not from the data: Claude's real answer, with every recipe number moved past
    the recipes it was shown, as a malformed answer could be."""
    [video] = [v for v in videos_to_fill(built) if v.id == SIX_MEALS_ID]
    answer = recorded_details(SIX_MEALS_ID)
    for item in answer.recipes:
        item.recipe += 10

    found = from_answer(video, [], answer)

    assert {d.source for d in found.values()} == {None}


def test_a_link_number_it_was_not_shown_finds_nothing(built: Engine) -> None:
    """Not from the data: Claude's real answer, with a link number one past the
    links it was shown, as a malformed answer could be."""
    [video] = [v for v in videos_to_fill(built) if v.id == SIX_MEALS_ID]
    pages = readable_pages(video)
    answer = recorded_details(SIX_MEALS_ID)
    stew = video.recipes[0].id
    assert from_answer(video, pages, answer)[stew].source == "link"
    answer.recipes[0].link = len(pages)  # one past the last

    assert from_answer(video, pages, answer)[stew].source is None


def test_text_with_no_line_really_written_there_finds_nothing(built: Engine) -> None:
    """Not from the data: Claude's real answer, with lines that aren't written in the
    description."""
    [video] = [v for v in videos_to_fill(built) if v.id == SIX_MEALS_ID]
    answer = recorded_details(SIX_MEALS_ID)
    assert answer.recipes[1].source == "description"
    answer.recipes[1].ingredients = copied(["2 cups vegan mayo"])
    answer.recipes[1].method = []

    found = from_answer(video, [], answer)

    assert found[video.recipes[1].id].source is None


def test_copied_lines_drops_links_in_a_line() -> None:
    # From the description of irTsXkAuZHg.
    line = "150 g vital wheat gluten (https://amzn.to/3dZgzsF)"

    found = copied_lines(copied([line]), f"Ingredients:\n{line}\n")
    assert texts(found) == ["150 g vital wheat gluten"]


@pytest.mark.parametrize(
    ("line", "written"),
    [
        # From SdN3xM_xALg's description and 8XRGh5C52x8's creator comment.
        ("1/2 cup cashews*", "💛 1/2 cup cashews*"),
        ("1 tablespoon olive oil, 15mL", "▢1 tablespoon olive oil, 15mL"),
        # From N_HsFfFg38g, which writes a recipe's ingredients on one line.
        (
            "2x garlic",
            "- red lentil minestrone | (4) {1x onion; 2x garlic; 2x carrots}",
        ),
    ],
)
def test_copied_lines_may_leave_out_symbols_and_split_items(
    line: str, written: str
) -> None:
    assert texts(copied_lines(copied([line]), written)) == [line]


@pytest.mark.parametrize(
    "description",
    [
        # From the descriptions of g2l3HHi2PBM, nYM8SaWvceM and TGA1sXv2BaE.
        "Start by prepping your veg: Chop and sauté 75g of baby mushrooms and chop "
        "100g of cherry tomatoes. \nWash a handful of spinach.\nNext make the muffin "
        "filling:\n Add 1 block of silken tofu, 2 tbsp of nutritional yeast",
        "Ingredients:\nRice Papers, firm tofu 150g, cabbage 160g, spring onion / "
        "chives 80g,",
        "Ingredients:\n\nGrated zucchinis\nDiced cherry tomatoes\nDiced onion",
    ],
)
def test_ingredients_in_sentences_or_under_a_heading_are_worth_asking_about(
    built: Engine, description: str
) -> None:
    [video] = [v for v in videos_to_fill(built) if v.id == SEITAN_ID]
    text = replace(video.text, description=description)

    assert plain_details(replace(video, text=text)) is None  # Claude is asked


def test_copied_lines_may_leave_out_a_chapter_timestamp() -> None:
    # From the description of eG0tXlljTtI, whose chapters are its steps.
    written = "0:52 ROUGHLY MASH THE TOFU AND MIX WELL\n2:35 DIVIDE INTO 4"
    steps = copied(["ROUGHLY MASH THE TOFU AND MIX WELL", "DIVIDE INTO 4"])

    assert texts(copied_lines(steps, written)) == [
        "ROUGHLY MASH THE TOFU AND MIX WELL",
        "DIVIDE INTO 4",
    ]


NOTE = (
    "*️⃣Note: Can make nut-free by replacing cashews with a seed like pumpkin, hemp, "
    "or sunflower or make no/low fat by replacing cashews with oat flour!"
)


def test_a_note_stays_where_it_was_written() -> None:
    # From the description of SdN3xM_xALg, whose cashews line has a footnote.
    written = f"💛 1/2 cup cashews*\n💛 1/2 cup nutritional yeast\n{NOTE}"
    lines = [
        AILine(text="1/2 cup cashews*", note=False),
        AILine(text="1/2 cup nutritional yeast", note=False),
        AILine(text=NOTE, note=True),
    ]

    assert copied_lines(lines, written) == [
        Line("1/2 cup cashews*"),
        Line("1/2 cup nutritional yeast"),
        Line(NOTE, note=True),
    ]


def test_a_method_is_kept_without_ingredients(built: Engine) -> None:
    """Not from the data: Claude's real answer, as if only the steps were written."""
    [video] = [v for v in videos_to_fill(built) if v.id == SIX_MEALS_ID]
    answer = recorded_details(SIX_MEALS_ID)
    description = video.text.description
    step = next(line for line in description.splitlines() if "BAKE for" in line)
    answer.recipes[5].ingredients = []
    answer.recipes[5].method = copied([step])

    found = from_answer(video, [], answer)[video.recipes[5].id]

    assert (found.source, found.ingredients) == ("description", None)
    assert found.method is not None and len(found.method) == 1


def test_lines_can_be_copied_from_the_text_of_a_page_without_recipe_data(
    built: Engine,
) -> None:
    """Not from the data: the page text is made up, from a page the six-meal video
    links to."""
    [video] = [v for v in videos_to_fill(built) if v.id == SIX_MEALS_ID]
    page = StoredPage(
        "https://minarome.substack.com/",
        "✍Written Instructions on my Substack",
        NO_RECIPE,
        None,
        "Peanut stew\n1 red bell pepper\n1-2 onions\nSubscribe",
    )
    answer = recorded_details(SIX_MEALS_ID)
    answer.recipes[0].link = 0
    answer.recipes[0].ingredients = copied(["1 red bell pepper", "1-2 onions"])

    found = from_answer(video, [page], answer)[video.recipes[0].id]

    assert (found.source, found.source_url) == ("link", page.url)
    assert found.ingredients == [Line("1 red bell pepper"), Line("1-2 onions")]


def test_copied_lines_may_straighten_quotes() -> None:
    # Not from the data: a line written with a curly quote, as nHr9LqK3PKc does.
    written = "1 can black beans (14oz = 400g)\nwhat you’re using"

    found = copied_lines(copied(["what you're using"]), written)

    assert texts(found) == ["what you're using"]
