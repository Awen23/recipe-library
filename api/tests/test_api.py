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


def test_rating_a_recipe_answers_with_its_marks(
    client: TestClient, split: Engine
) -> None:
    oats = recipe_id(split, "Overnight oats")

    response = client.put(f"/recipes/{oats}/rating", json={"rating": "would_cook"})

    assert response.status_code == 200
    body = response.json()
    assert (body["rating"], body["hidden"]) == ("would_cook", False)


def test_a_rating_can_be_cleared_with_null(client: TestClient, split: Engine) -> None:
    oats = recipe_id(split, "Overnight oats")
    client.put(f"/recipes/{oats}/rating", json={"rating": "curious"})

    response = client.put(f"/recipes/{oats}/rating", json={"rating": None})

    assert response.json()["rating"] is None


def test_hiding_a_recipe_keeps_its_rating(client: TestClient, split: Engine) -> None:
    bars = recipe_id(split, "Raspberry oat bars")
    client.put(f"/recipes/{bars}/rating", json={"rating": "curious"})

    response = client.put(f"/recipes/{bars}/hidden", json={"hidden": True})

    body = response.json()
    assert (body["rating"], body["hidden"]) == ("curious", True)


def test_a_hidden_recipe_can_be_shown_again(client: TestClient, split: Engine) -> None:
    bars = recipe_id(split, "Raspberry oat bars")
    client.put(f"/recipes/{bars}/hidden", json={"hidden": True})

    response = client.put(f"/recipes/{bars}/hidden", json={"hidden": False})

    assert response.json()["hidden"] is False


def test_a_rating_that_isnt_a_level_is_refused(
    client: TestClient, split: Engine
) -> None:
    """Not from the data: a made-up rating."""
    oats = recipe_id(split, "Overnight oats")

    response = client.put(f"/recipes/{oats}/rating", json={"rating": "5 stars"})

    assert response.status_code == 422


def test_a_rating_must_be_given_even_to_clear_it(
    client: TestClient, split: Engine
) -> None:
    """Not from the data: a body without its field, so a typo can't clear a
    rating."""
    oats = recipe_id(split, "Overnight oats")

    response = client.put(f"/recipes/{oats}/rating", json={"ratnig": "curious"})

    assert response.status_code == 422


def test_marking_a_recipe_that_isnt_stored_is_not_found(client: TestClient) -> None:
    """Not from the data: an ID no recipe has."""
    response = client.put("/recipes/9999/hidden", json={"hidden": True})

    assert response.status_code == 404
    assert response.json() == {"detail": "No recipe has the ID 9999."}


def test_the_app_wont_start_on_an_old_database(
    engine: Engine, alembic_config: Config
) -> None:
    """Not from the data: the database is a migration behind."""
    command.downgrade(alembic_config, "-1")

    with pytest.raises(RuntimeError, match="alembic upgrade head"), TestClient(app):
        pass
