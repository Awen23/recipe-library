"""The HTTP API, called the way the UI will call it."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from recipes.entrypoints.api import app
from recipes.storage import recipes


@pytest.fixture
def client(split: Engine) -> Iterator[TestClient]:
    """The app, on the database `split` set up: `DATABASE_URL` points at it. The
    `with` runs the app's startup and shutdown."""
    with TestClient(app) as client:
        yield client


def recipe_id(engine: Engine, name: str) -> int:
    with engine.connect() as connection:
        found = connection.scalar(select(recipes.c.id).where(recipes.c.name == name))
    assert found is not None, name
    return found


def test_setting_interest_answers_with_the_ratings(
    client: TestClient, split: Engine
) -> None:
    oats = recipe_id(split, "Overnight oats")

    response = client.put(f"/recipes/{oats}/interest", json={"interest": "curious"})

    assert response.status_code == 200
    body = response.json()
    assert (body["interest"], body["verdict"]) == ("curious", None)


def test_interest_can_be_cleared_with_null(client: TestClient, split: Engine) -> None:
    oats = recipe_id(split, "Overnight oats")
    client.put(f"/recipes/{oats}/interest", json={"interest": "not_for_me"})

    response = client.put(f"/recipes/{oats}/interest", json={"interest": None})

    assert response.json()["interest"] is None


def test_a_verdict_keeps_the_interest(client: TestClient, split: Engine) -> None:
    bars = recipe_id(split, "Raspberry oat bars")
    client.put(f"/recipes/{bars}/interest", json={"interest": "want_to_cook"})

    response = client.put(f"/recipes/{bars}/verdict", json={"verdict": "regularly"})

    body = response.json()
    assert (body["interest"], body["verdict"]) == ("want_to_cook", "regularly")


def test_a_verdict_can_be_cleared_with_null(client: TestClient, split: Engine) -> None:
    bars = recipe_id(split, "Raspberry oat bars")
    client.put(f"/recipes/{bars}/verdict", json={"verdict": "not_again"})

    response = client.put(f"/recipes/{bars}/verdict", json={"verdict": None})

    assert response.json()["verdict"] is None


@pytest.mark.parametrize(
    ("rating", "body"),
    [("interest", {"interest": "5 stars"}), ("verdict", {"verdict": "loved it"})],
    ids=str,
)
def test_a_rating_that_isnt_one_of_its_levels_is_refused(
    client: TestClient, split: Engine, rating: str, body: dict[str, str]
) -> None:
    """Not from the data: made-up levels."""
    oats = recipe_id(split, "Overnight oats")

    response = client.put(f"/recipes/{oats}/{rating}", json=body)

    assert response.status_code == 422


def test_a_rating_must_be_given_even_to_clear_it(
    client: TestClient, split: Engine
) -> None:
    """Not from the data: a body without its field, so a typo can't clear a
    rating."""
    oats = recipe_id(split, "Overnight oats")

    response = client.put(f"/recipes/{oats}/interest", json={"intrest": "curious"})

    assert response.status_code == 422


def test_rating_a_recipe_that_isnt_stored_is_not_found(client: TestClient) -> None:
    """Not from the data: an ID no recipe has."""
    response = client.put("/recipes/9999/verdict", json={"verdict": "regularly"})

    assert response.status_code == 404
    assert response.json() == {"detail": "No recipe has the ID 9999."}


def test_the_app_wont_start_on_an_old_database(
    engine: Engine, alembic_config: Config
) -> None:
    """Not from the data: the database is a migration behind."""
    command.downgrade(alembic_config, "-1")

    with pytest.raises(RuntimeError, match="alembic upgrade head"), TestClient(app):
        pass
