from typing import Any

import httpx2
import pytest
from sqlalchemy import Engine, select, update

from recipes.ai import AIKeyError, Claude
from recipes.building import build_recipes, fill_details
from recipes.fetching import fetch_linked_pages
from recipes.storage import recipes

from fakes import FakeClaudeApi, FakeWeb, read_page

MEAL_PREP_ID = "whr7iOKRXTA"  # a meal prep video with five recipes


@pytest.fixture
def fake_claude() -> FakeClaudeApi:
    return FakeClaudeApi()


def build(engine: Engine, fake_claude: FakeClaudeApi):  # type: ignore[no-untyped-def]
    with Claude("test-key", transport=fake_claude.transport) as claude:
        return build_recipes(engine, claude)


def recipe_rows(engine: Engine) -> list[tuple[int, str, str]]:
    with engine.connect() as connection:
        query = select(recipes.c.id, recipes.c.video_id, recipes.c.name)
        return [tuple(row) for row in connection.execute(query.order_by(recipes.c.id))]


def test_build_stores_each_videos_recipes(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    summary = build(fetched, fake_claude)

    # 5 + 6 + 1 + 1 + 1 recipes in Claude's recorded answers.
    assert (summary.videos, summary.recipes, summary.failed) == (5, 14, {})
    assert len(fake_claude.requests) == 5
    assert (MEAL_PREP_ID, "Raspberry oat bars") in [r[1:] for r in recipe_rows(fetched)]


def test_building_again_leaves_the_recipes_alone(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    build(fetched, fake_claude)
    before = recipe_rows(fetched)

    summary = build(fetched, fake_claude)

    assert summary.videos == 0
    assert len(fake_claude.requests) == 5  # all from the first build
    assert recipe_rows(fetched) == before


def test_a_video_claude_couldnt_answer_about_is_left_for_the_next_build(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    """Not from the data: the error follows the shape in Anthropic's error docs."""
    error = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "x"},
    }
    fake_claude.queue.append(httpx2.Response(400, json=error))  # the first video

    summary = build(fetched, fake_claude)

    # H0tkAEL6CS8 is asked about first, and has one recipe.
    assert (summary.videos, summary.recipes) == (4, 13)
    assert list(summary.failed) == ["H0tkAEL6CS8"]
    assert build(fetched, fake_claude).videos == 1  # the next build asks again


def test_a_rejected_api_key_stops_the_build(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    """Not from the data: the error follows the shape in Anthropic's error docs."""
    error = {"type": "error", "error": {"type": "authentication_error", "message": "x"}}
    fake_claude.queue.append(httpx2.Response(401, json=error))

    with pytest.raises(AIKeyError):
        build(fetched, fake_claude)
    assert len(fake_claude.requests) == 1


OATMEAL_ID = "gOxwhuntyMY"  # one recipe, with one link
OATMEAL_URL = "https://goodfoodbaddie.com/blueberry-baked-oatmeal/"


def fetch_oatmeal_page(engine: Engine) -> None:
    """Fetch every fixture video's links, from a web that only has the oatmeal page."""
    page = httpx2.Response(
        200,
        headers={"content-type": "text/html; charset=utf-8"},
        text=read_page("blueberry_baked_oatmeal.html"),
    )
    with FakeWeb({OATMEAL_URL: page}).fetcher() as fetcher:
        fetch_linked_pages(engine, fetcher)


def details(engine: Engine) -> list[tuple[Any, ...]]:
    with engine.connect() as connection:
        query = select(
            recipes.c.video_id,
            recipes.c.ingredients,
            recipes.c.method,
            recipes.c.source,
            recipes.c.source_url,
            recipes.c.details_by,
        ).where(recipes.c.source.is_not(None))
        return [tuple(row) for row in connection.execute(query)]


def test_fill_gives_recipes_the_details_on_their_page(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    build(fetched, fake_claude)
    fetch_oatmeal_page(fetched)

    assert fill_details(fetched) == 1
    [(video_id, ingredients, method, source, source_url, by)] = details(fetched)
    assert (video_id, source, source_url, by) == (
        OATMEAL_ID,
        "link",
        OATMEAL_URL,
        "code",
    )
    assert ingredients[0] == "2 1/2 cups Rolled Oats (ensure gluten-free if necessary)"
    assert len(ingredients) == 11
    assert method[0] == "Preheat the oven to 375°F."


def test_filling_again_leaves_details_alone(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    build(fetched, fake_claude)
    fetch_oatmeal_page(fetched)
    fill_details(fetched)
    with fetched.begin() as connection:  # as if corrected by hand
        connection.execute(
            update(recipes)
            .where(recipes.c.video_id == OATMEAL_ID)
            .values(ingredients=["3 cups oats"], details_by="hand")
        )

    assert fill_details(fetched) == 0
    assert details(fetched)[0][1] == ["3 cups oats"]
