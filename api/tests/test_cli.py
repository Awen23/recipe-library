from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from recipes.entrypoints import cli
from recipes.storage import videos
from recipes.youtube import YouTubeClient

from fakes import FakeYouTubeApi


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test in an empty folder with its own .env, so the real .env and
    data/ are never touched."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)  # set again by `engine`
    Path(".env").write_text("YOUTUBE_API_KEY=test-key\n", encoding="utf-8")


def test_fetch_saves_the_playlist(
    monkeypatch: pytest.MonkeyPatch,
    fake_api: FakeYouTubeApi,
    engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Make the CLI's YouTubeClient talk to the fake instead of the real API.
    fake_client = partial(YouTubeClient, transport=fake_api.transport)
    monkeypatch.setattr(cli, "YouTubeClient", fake_client)

    assert cli.main(["fetch", "PLAYLIST_ID"]) == 0

    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(videos)) == 5
    assert "Saved 5 videos (5 new)" in capsys.readouterr().out
    assert fake_api.requests[0].headers["X-Goog-Api-Key"] == "test-key"


def test_fetch_without_an_api_key_says_how_to_set_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    Path(".env").unlink()

    assert cli.main(["fetch", "PLAYLIST_ID"]) == 1
    assert "YOUTUBE_API_KEY is not set" in capsys.readouterr().err


def test_fetch_before_migrating_says_how_to_create_the_tables(
    monkeypatch: pytest.MonkeyPatch,
    fake_api: FakeYouTubeApi,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli, "YouTubeClient", partial(YouTubeClient, transport=fake_api.transport)
    )

    # The test runs in an empty folder, so data/recipes.db is new, with no migrations.
    assert cli.main(["fetch", "PLAYLIST_ID"]) == 1
    assert "alembic upgrade head" in capsys.readouterr().err
    assert fake_api.requests == []  # nothing was fetched


def test_no_command_shows_the_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])

    assert exit_info.value.code == 2
    assert "usage: recipes" in capsys.readouterr().err
