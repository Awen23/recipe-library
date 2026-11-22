from typing import Any

import httpx2
import pytest
from sqlalchemy import Engine, select, update

from recipes.ai import Claude
from recipes.building import DetailsSummary, build_recipes, fill_details
from recipes.details import copied_lines, from_answer
from recipes.fetching import fetch_linked_pages
from recipes.storage import recipes, videos_to_fill

from fakes import FakeClaudeApi, FakeWeb, read_fixture, read_page, recorded_details

# The fixture videos' links that lead to recipe pages, and the trimmed pages.
PAGES = {
    "https://goodfoodbaddie.com/blueberry-baked-oatmeal/": (
        "blueberry_baked_oatmeal.html"
    ),
    "https://makeitdairyfree.com/one-pot-west-african-peanut-stew-vegan/": (
        "west_african_peanut_stew.html"
    ),
    "https://www.theedgyveg.com/2023/04/24/3-ingredient-vegan-brownies/": (
        "vegan_brownies.html"
    ),
}
OATMEAL_ID = "gOxwhuntyMY"  # one recipe, with a link to its page
SIX_MEALS_ID = "nHr9LqK3PKc"  # six recipes: one on a linked page, five in the text
SEITAN_ID = "eG0tXlljTtI"  # its description is trimmed, so it has nothing to read


@pytest.fixture
def fake_claude() -> FakeClaudeApi:
    return FakeClaudeApi()


@pytest.fixture
def built(fetched: Engine, fake_claude: FakeClaudeApi) -> Engine:
    """The fixture videos split into recipes, with their links fetched from a web
    that has only the three recipe pages."""
    web = FakeWeb(
        {
            url: httpx2.Response(
                200, headers={"content-type": "text/html"}, text=read_page(name)
            )
            for url, name in PAGES.items()
        }
    )
    with web.fetcher() as fetcher:
        fetch_linked_pages(fetched, fetcher)
    with Claude("test-key", transport=fake_claude.transport) as claude:
        build_recipes(fetched, claude)
    return fetched


def fill(engine: Engine, fake_claude: FakeClaudeApi) -> DetailsSummary:
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
    assert oatmeal["ingredients"][0] == (
        "2 1/2 cups Rolled Oats (ensure gluten-free if necessary)"
    )


def test_claude_is_asked_only_about_videos_plain_code_cant_settle(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    before = len(fake_claude.requests)

    summary = fill(built, fake_claude)

    # The meal prep and six-meal videos. The oatmeal and brownies have one recipe
    # and a recipe page, and the seitan video has nothing to read.
    assert (summary.videos, summary.asked, summary.failed) == (5, 2, {})
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
    assert patties["ingredients"][0] == "400g firm tofu (14oz)"


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

    assert fill(built, fake_claude).videos == 0
    assert len(fake_claude.requests) == before
    assert details(built, OATMEAL_ID)[0]["ingredients"] == ["3 cups oats"]


def test_a_video_claude_couldnt_answer_about_is_left_for_the_next_build(
    built: Engine, fake_claude: FakeClaudeApi
) -> None:
    """Not from the data: the error follows the shape in Anthropic's error docs."""
    error = {"type": "error", "error": {"type": "overloaded_error", "message": "x"}}
    fake_claude.queue.append(httpx2.Response(400, json=error))

    summary = fill(built, fake_claude)

    assert len(summary.failed) == 1
    assert fill(built, fake_claude).asked == 1


def test_videos_wait_until_their_links_are_fetched(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    with Claude("test-key", transport=fake_claude.transport) as claude:
        build_recipes(fetched, claude)

    # Only the seitan video has no links to fetch.
    assert [video.id for video in videos_to_fill(fetched)] == [SEITAN_ID]


def test_copied_lines_keeps_only_lines_in_the_text() -> None:
    description = read_fixture("descriptions.json")[SIX_MEALS_ID]
    lines = [
        "400g firm tofu (14oz)",
        "1  medium sized onion,   minced",  # spaced differently
        "2 cups vegan mayo",  # Not from the data: a line that isn't written there
    ]

    assert copied_lines(lines, description) == lines[:2]


def test_an_answer_with_numbers_out_of_range_finds_nothing(
    built: Engine,
) -> None:
    """Not from the data: Claude's real answer, with its numbers broken on purpose."""
    [video] = [v for v in videos_to_fill(built) if v.id == SIX_MEALS_ID]
    answer = recorded_details(SIX_MEALS_ID)
    for item in answer.recipes:
        item.recipe += 10

    found = from_answer(video, [], answer)

    assert {d.source for d in found.values()} == {None}


def test_a_link_number_out_of_range_finds_nothing(built: Engine) -> None:
    """Not from the data: Claude's real answer, with its link number broken."""
    [video] = [v for v in videos_to_fill(built) if v.id == SIX_MEALS_ID]
    answer = recorded_details(SIX_MEALS_ID)
    assert answer.recipes[0].source == "link"
    answer.recipes[0].link = 99

    found = from_answer(video, [], answer)

    assert found[video.recipes[0].id].source is None


def test_text_with_no_line_really_written_there_finds_nothing(built: Engine) -> None:
    """Not from the data: Claude's real answer, with lines that aren't written in the
    description."""
    [video] = [v for v in videos_to_fill(built) if v.id == SIX_MEALS_ID]
    answer = recorded_details(SIX_MEALS_ID)
    assert answer.recipes[1].source == "description"
    answer.recipes[1].ingredients = ["2 cups vegan mayo"]

    found = from_answer(video, [], answer)

    assert found[video.recipes[1].id].source is None
