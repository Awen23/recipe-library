from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from recipes.ai import Claude
from recipes.entrypoints import cli
from recipes.storage import recipes, videos
from recipes.youtube import YouTubeClient

from fakes import FakeClaudeApi, FakeWeb, FakeYouTubeApi


@pytest.fixture(autouse=True)
def isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_web: FakeWeb
) -> None:
    """Run each test in an empty folder with its own .env, so the real .env and
    data/ are never touched, and fetch pages from a fake web that has none."""
    monkeypatch.setattr(cli, "PageFetcher", fake_web.fetcher)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)  # set again by `engine`
    Path(".env").write_text(
        "YOUTUBE_API_KEY=test-key\nANTHROPIC_API_KEY=test-key\n", encoding="utf-8"
    )


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
    output = capsys.readouterr().out
    assert "Saved 5 videos (5 new)" in output
    assert fake_api.requests[0].headers["X-Goog-Api-Key"] == "test-key"
    # The fake web answers every link with a 404.
    assert "Fetched 3 links from 3 videos (0 with a recipe)" in output


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


def test_build_asks_claude_about_each_video_and_saves_the_recipes(
    monkeypatch: pytest.MonkeyPatch,
    fake_api: FakeYouTubeApi,
    engine: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli, "YouTubeClient", partial(YouTubeClient, transport=fake_api.transport)
    )
    fake_claude = FakeClaudeApi()
    monkeypatch.setattr(cli, "Claude", partial(Claude, transport=fake_claude.transport))
    cli.main(["fetch", "PLAYLIST_ID"])

    assert cli.main(["build"]) == 0

    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(recipes)) == 14
    assert "Built 14 recipes from 5 new videos" in capsys.readouterr().out


def test_build_without_an_api_key_says_how_to_set_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    Path(".env").write_text("YOUTUBE_API_KEY=test-key\n", encoding="utf-8")

    assert cli.main(["build"]) == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err
