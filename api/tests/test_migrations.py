"""The migrations in `migrations/`, run the way `alembic upgrade head` runs them."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import insert, inspect
from sqlalchemy.exc import IntegrityError

from recipes.storage import chapters, create_engine

PYPROJECT = Path(__file__).parents[1] / "pyproject.toml"  # holds Alembic's settings
TABLES = {"channels", "videos", "chapters", "creator_comments"}


@pytest.fixture
def alembic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Alembic's settings, pointed at a new, empty database for each test."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'recipes.db'}")
    return Config(toml_file=PYPROJECT)


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
