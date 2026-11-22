"""The migrations in `migrations/`, run the way `alembic upgrade head` runs them."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from recipes.storage import create_engine

PYPROJECT = Path(__file__).parents[1] / "pyproject.toml"  # holds Alembic's settings


def test_upgrade_runs_on_a_new_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'recipes.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    command.upgrade(Config(toml_file=PYPROJECT), "head")

    # Alembic records which migrations have run in this table.
    assert inspect(create_engine(url)).has_table("alembic_version")
