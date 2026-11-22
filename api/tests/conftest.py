"""Shared fixtures. pytest loads this file itself; tests use its fixtures by name."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from recipes.storage import PYPROJECT, create_engine

from fakes import FakeYouTubeApi


@pytest.fixture
def fake_api() -> FakeYouTubeApi:
    return FakeYouTubeApi()


@pytest.fixture
def alembic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Alembic's settings, pointed at a new, empty database for each test.

    `DATABASE_URL` is set for the whole test, so the app's own `create_engine()`
    connects to the same database.
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'recipes.db'}")
    return Config(toml_file=PYPROJECT)


@pytest.fixture
def engine(alembic_config: Config) -> Engine:
    """A new database with every migration run, like `alembic upgrade head`."""
    command.upgrade(alembic_config, "head")
    return create_engine()
