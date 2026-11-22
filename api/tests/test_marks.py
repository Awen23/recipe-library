"""Rating and hiding recipes: the marks I set by hand, in `recipe_marks`."""

from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import Engine, insert, select
from sqlalchemy.exc import IntegrityError

from recipes.ai import Claude
from recipes.building import build_recipes, fill_details
from recipes.storage import (
    NoSuchRecipeError,
    hide_recipe,
    rate_recipe,
    recipe_marks,
    recipes,
)

from fakes import FakeClaudeApi

MEAL_PREP_ID = "whr7iOKRXTA"  # a meal prep video with five recipes
MONDAY = datetime(2026, 11, 23, 18, 0)
TUESDAY = datetime(2026, 11, 24, 18, 0)


@pytest.fixture
def built(fetched: Engine) -> Engine:
    """The five fixture videos split into their recipes, from Claude's real
    answers."""
    with Claude("test-key", transport=FakeClaudeApi().transport) as claude:
        build_recipes(fetched, claude)
    return fetched


def recipe_id(engine: Engine, name: str) -> int:
    with engine.connect() as connection:
        found = connection.scalar(select(recipes.c.id).where(recipes.c.name == name))
    assert found is not None, name
    return found


def marks(engine: Engine) -> dict[int, dict[str, Any]]:
    """Every recipe's marks, by recipe ID."""
    with engine.connect() as connection:
        rows = connection.execute(select(recipe_marks)).mappings()
        return {row["recipe_id"]: dict(row) for row in rows}


def test_rating_a_recipe_stores_the_rating(built: Engine) -> None:
    oats = recipe_id(built, "Overnight oats")

    rate_recipe(built, oats, "would_cook", now=MONDAY)

    assert marks(built) == {
        oats: {
            "recipe_id": oats,
            "rating": "would_cook",
            "hidden": False,
            "updated_at": MONDAY,
        }
    }


def test_rating_again_changes_the_rating(built: Engine) -> None:
    oats = recipe_id(built, "Overnight oats")
    rate_recipe(built, oats, "would_cook", now=MONDAY)

    rate_recipe(built, oats, "curious", now=TUESDAY)

    assert (marks(built)[oats]["rating"], marks(built)[oats]["updated_at"]) == (
        "curious",
        TUESDAY,
    )


def test_a_rating_can_be_cleared(built: Engine) -> None:
    oats = recipe_id(built, "Overnight oats")
    rate_recipe(built, oats, "not_for_me")

    rate_recipe(built, oats, None)

    assert marks(built)[oats]["rating"] is None


def test_hiding_a_recipe_keeps_its_rating(built: Engine) -> None:
    bars = recipe_id(built, "Raspberry oat bars")
    rate_recipe(built, bars, "curious")

    hide_recipe(built, bars)

    assert (marks(built)[bars]["rating"], marks(built)[bars]["hidden"]) == (
        "curious",
        True,
    )


def test_a_hidden_recipe_can_be_shown_again(built: Engine) -> None:
    bars = recipe_id(built, "Raspberry oat bars")
    hide_recipe(built, bars)

    hide_recipe(built, bars, hidden=False)

    assert marks(built)[bars]["hidden"] is False


def test_marking_one_recipe_leaves_the_others_unmarked(built: Engine) -> None:
    # The meal prep video's other four recipes have no row, so they're unrated and
    # shown.
    hide_recipe(built, recipe_id(built, "Hearty vegan lasagne"))

    assert len(marks(built)) == 1


def test_a_recipe_that_isnt_stored_cant_be_marked(built: Engine) -> None:
    """Not from the data: an ID no recipe has."""
    with pytest.raises(NoSuchRecipeError):
        rate_recipe(built, 9999, "would_cook")

    assert marks(built) == {}


def test_marks_survive_building_again(built: Engine) -> None:
    oats = recipe_id(built, "Overnight oats")
    rate_recipe(built, oats, "would_cook", now=MONDAY)
    hide_recipe(built, oats, now=MONDAY)
    before = marks(built)

    # The same steps as `recipes build`: recipes, then their details.
    with Claude("test-key", transport=FakeClaudeApi().transport) as claude:
        build_recipes(built, claude)
        fill_details(built, claude)

    assert marks(built) == before


def test_a_rating_must_be_one_of_the_levels(built: Engine) -> None:
    """Not from the data: checks the rule in the table, with a made-up rating."""
    oats = recipe_id(built, "Overnight oats")
    row = {"recipe_id": oats, "rating": "5 stars", "hidden": False}

    with built.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(insert(recipe_marks).values(**row, updated_at=MONDAY))
