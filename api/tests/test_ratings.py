"""The ratings I set by hand on recipes, in `recipe_ratings`: my interest before cooking
one, and my verdict after."""

from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import Engine, insert, select
from sqlalchemy.exc import IntegrityError

from recipes.ai import Claude
from recipes.building import build_recipes, fill_details
from recipes.models import Ratings
from recipes.storage import (
    NoSuchRecipeError,
    recipe_ratings,
    recipes,
    set_interest,
    set_verdict,
)

from fakes import FakeClaudeApi

MONDAY = datetime(2026, 11, 23, 18, 0)
TUESDAY = datetime(2026, 11, 24, 18, 0)


def recipe_id(engine: Engine, name: str) -> int:
    with engine.connect() as connection:
        found = connection.scalar(select(recipes.c.id).where(recipes.c.name == name))
    assert found is not None, name
    return found


def ratings(engine: Engine) -> dict[int, dict[str, Any]]:
    """Every recipe's ratings, by recipe ID."""
    with engine.connect() as connection:
        rows = connection.execute(select(recipe_ratings)).mappings()
        return {row["recipe_id"]: dict(row) for row in rows}


def test_setting_interest_stores_it(split: Engine) -> None:
    oats = recipe_id(split, "Overnight oats")

    set_interest(split, oats, "want_to_cook", now=MONDAY)

    assert ratings(split) == {
        oats: {
            "recipe_id": oats,
            "interest": "want_to_cook",
            "verdict": None,
            "updated_at": MONDAY,
        }
    }


def test_setting_interest_answers_with_the_ratings(split: Engine) -> None:
    oats = recipe_id(split, "Overnight oats")

    found = set_interest(split, oats, "curious", now=MONDAY)

    assert found == Ratings(interest="curious", verdict=None, updated_at=MONDAY)


def test_setting_interest_again_changes_it(split: Engine) -> None:
    oats = recipe_id(split, "Overnight oats")
    set_interest(split, oats, "want_to_cook", now=MONDAY)

    set_interest(split, oats, "not_for_me", now=TUESDAY)

    assert (ratings(split)[oats]["interest"], ratings(split)[oats]["updated_at"]) == (
        "not_for_me",
        TUESDAY,
    )


def test_interest_can_be_cleared(split: Engine) -> None:
    oats = recipe_id(split, "Overnight oats")
    set_interest(split, oats, "curious")

    set_interest(split, oats, None)

    assert ratings(split)[oats]["interest"] is None


def test_a_verdict_keeps_the_interest(split: Engine) -> None:
    bars = recipe_id(split, "Raspberry oat bars")
    set_interest(split, bars, "want_to_cook")

    set_verdict(split, bars, "special_occasion")

    assert (ratings(split)[bars]["interest"], ratings(split)[bars]["verdict"]) == (
        "want_to_cook",
        "special_occasion",
    )


def test_a_verdict_can_be_cleared(split: Engine) -> None:
    bars = recipe_id(split, "Raspberry oat bars")
    set_verdict(split, bars, "not_again")

    set_verdict(split, bars, None)

    assert ratings(split)[bars]["verdict"] is None


def test_rating_one_recipe_leaves_the_others_unrated(split: Engine) -> None:
    # The meal prep video's other four recipes have no row, so they have no ratings.
    set_verdict(split, recipe_id(split, "Hearty vegan lasagne"), "regularly")

    assert len(ratings(split)) == 1


def test_a_recipe_that_isnt_stored_cant_be_rated(split: Engine) -> None:
    """Not from the data: an ID no recipe has."""
    with pytest.raises(NoSuchRecipeError):
        set_interest(split, 9999, "want_to_cook")

    assert ratings(split) == {}


def test_ratings_survive_building_again(split: Engine) -> None:
    oats = recipe_id(split, "Overnight oats")
    set_interest(split, oats, "want_to_cook", now=MONDAY)
    set_verdict(split, oats, "regularly", now=MONDAY)
    before = ratings(split)

    # The same steps as `recipes build`: recipes, then their details.
    with Claude("test-key", transport=FakeClaudeApi().transport) as claude:
        build_recipes(split, claude)
        fill_details(split, claude)

    assert ratings(split) == before


@pytest.mark.parametrize(
    "rating", [{"interest": "5 stars"}, {"verdict": "loved it"}], ids=str
)
def test_each_rating_must_be_one_of_its_levels(
    split: Engine, rating: dict[str, str]
) -> None:
    """Not from the data: checks the rules in the table, with made-up levels."""
    oats = recipe_id(split, "Overnight oats")

    with split.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            insert(recipe_ratings).values(recipe_id=oats, updated_at=MONDAY, **rating)
        )
