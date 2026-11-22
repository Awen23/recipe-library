"""Shared fixtures. pytest loads this file itself; tests use its fixtures by name."""

from dataclasses import replace
from pathlib import Path

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from recipes.playlist import fetch_playlist
from recipes.storage import PYPROJECT, create_engine, save_playlist
from recipes.youtube import YouTubeClient

from fakes import FakeWeb, FakeYouTubeApi, read_fixture, recipe_web


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any real request fail, so a test that forgets a fake can't reach a real
    site. The fakes use httpx2's MockTransport, which this doesn't touch."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Tests don't use the network. Use a fake from fakes.py.")

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", refuse)


@pytest.fixture
def fake_web() -> FakeWeb:
    return recipe_web()


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


@pytest.fixture
def fetched(engine: Engine, fake_api: FakeYouTubeApi) -> Engine:
    """The five fixture videos stored, with full descriptions where there are some."""
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        playlist = fetch_playlist(client, "PLAYLIST_ID")
    descriptions = read_fixture("descriptions.json")
    full = tuple(
        replace(video, description=descriptions.get(video.id, video.description))
        for video in playlist.videos
    )
    save_playlist(replace(playlist, videos=full), engine)
    return engine
