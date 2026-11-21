import json
from functools import partial
from pathlib import Path

import pytest

from recipes.entrypoints import cli
from recipes.youtube import YouTubeClient

from fakes import FakeYouTubeApi


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test in an empty folder with its own .env, so the real .env and
    data/ are never touched."""
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text("YOUTUBE_API_KEY=test-key\n", encoding="utf-8")


def test_fetch_saves_the_playlist(
    monkeypatch: pytest.MonkeyPatch,
    fake_api: FakeYouTubeApi,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Make the CLI's YouTubeClient talk to the fake instead of the real API.
    fake_client = partial(YouTubeClient, transport=fake_api.transport)
    monkeypatch.setattr(cli, "YouTubeClient", fake_client)

    assert cli.main(["PLAYLIST_ID"]) == 0

    saved = json.loads(Path("data/playlist.json").read_text(encoding="utf-8"))
    assert len(saved["videos"]) == 5
    assert "Saved 5 videos" in capsys.readouterr().out
    assert fake_api.requests[0].headers["X-Goog-Api-Key"] == "test-key"


def test_fetch_without_an_api_key_says_how_to_set_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    Path(".env").unlink()

    assert cli.main(["PLAYLIST_ID"]) == 1
    assert "YOUTUBE_API_KEY is not set" in capsys.readouterr().err
