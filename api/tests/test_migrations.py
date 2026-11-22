"""The migrations in `migrations/`, run the way `alembic upgrade head` runs them."""

from datetime import datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import insert, inspect
from sqlalchemy.exc import IntegrityError

from recipes.storage import channels, chapters, create_engine, recipes, videos

TABLES = {
    "channels",
    "videos",
    "chapters",
    "creator_comments",
    "recipes",
    "recipe_links",
    "recipe_ratings",
}


def test_upgrade_creates_the_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    # Alembic records which migrations have run in `alembic_version`.
    tables = set(inspect(create_engine()).get_table_names())
    assert tables == TABLES | {"alembic_version"}


def test_migrations_match_the_tables_in_storage(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    # Fails if a table in storage.py was changed without a migration to match.
    command.check(alembic_config)


def test_downgrade_removes_the_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    command.downgrade(alembic_config, "base")

    assert set(inspect(create_engine()).get_table_names()) == {"alembic_version"}


def test_a_chapter_needs_its_video_to_be_stored(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    chapter = {"video_id": "whr7iOKRXTA", "position": 0, "start_seconds": 0}

    # No video has been stored, so the foreign key rejects this.
    with create_engine().begin() as connection, pytest.raises(IntegrityError):
        connection.execute(insert(chapters).values(**chapter, title="Intro"))


def test_a_recipe_says_who_set_each_field(alembic_config: Config) -> None:
    """Not from the data: checks the rule, with a made-up `_by`."""
    command.upgrade(alembic_config, "head")
    with create_engine().begin() as connection:
        connection.execute(insert(channels).values(id="UC1", title="A channel"))
        connection.execute(insert(videos).values(**VIDEO, channel_id="UC1"))
        recipe = {"video_id": VIDEO["id"], "position": 0, "name": "Mayak tofu"}

        with pytest.raises(IntegrityError):
            connection.execute(
                insert(recipes).values(**recipe, name_by="guess", start_by="code")
            )


def test_details_say_who_set_them(alembic_config: Config) -> None:
    """Not from the data: checks the rule added after the table, with a made-up
    `details_by`."""
    command.upgrade(alembic_config, "head")
    with create_engine().begin() as connection:
        connection.execute(insert(channels).values(id="UC1", title="A channel"))
        connection.execute(insert(videos).values(**VIDEO, channel_id="UC1"))
        recipe = {"video_id": VIDEO["id"], "position": 0, "name": "Mayak tofu"}

        with pytest.raises(IntegrityError):
            connection.execute(
                insert(recipes).values(
                    **recipe, name_by="code", start_by="code", details_by="guess"
                )
            )


# Not from the data: the fewest fields a stored video needs.
VIDEO = {
    "id": "vM3y-Wsxa24",
    "title": "A video",
    "description": "",
    "duration_seconds": 60,
    "published_at": datetime(2026, 1, 1),
    "thumbnail_url": "https://i.ytimg.com/vi/vM3y-Wsxa24/mqdefault.jpg",
    "embeddable": True,
    "first_seen_at": datetime(2026, 1, 1),
}
