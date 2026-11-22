from dataclasses import replace

import httpx2
import pytest
from sqlalchemy import Engine, select

from recipes.ai import AIKeyError, Claude
from recipes.building import build_recipes
from recipes.playlist import Playlist, fetch_playlist
from recipes.storage import recipes, save_playlist
from recipes.youtube import YouTubeClient

from fakes import FakeClaudeApi, FakeYouTubeApi, read_fixture


@pytest.fixture
def fetched(engine: Engine, fake_api: FakeYouTubeApi) -> Engine:
    """The five fixture videos stored, with full descriptions where there are some."""
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        playlist: Playlist = fetch_playlist(client, "PLAYLIST_ID")
    descriptions = read_fixture("descriptions.json")
    full = tuple(
        replace(video, description=descriptions.get(video.id, video.description))
        for video in playlist.videos
    )
    save_playlist(replace(playlist, videos=full), engine)
    return engine


@pytest.fixture
def fake_claude() -> FakeClaudeApi:
    return FakeClaudeApi()


def build(engine: Engine, fake_claude: FakeClaudeApi):  # type: ignore[no-untyped-def]
    with Claude("test-key", transport=fake_claude.transport) as claude:
        return build_recipes(engine, claude)


def recipe_rows(engine: Engine) -> list[tuple[int, str, str]]:
    with engine.connect() as connection:
        query = select(recipes.c.id, recipes.c.video_id, recipes.c.name)
        return [tuple(row) for row in connection.execute(query.order_by(recipes.c.id))]


def test_build_stores_each_videos_recipes(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    summary = build(fetched, fake_claude)

    # 5 + 6 + 1 + 1 + 1 recipes in Claude's recorded answers.
    assert (summary.videos, summary.recipes, summary.failed) == (5, 14, {})
    assert len(fake_claude.requests) == 5
    assert ("whr7iOKRXTA", "Raspberry oat bars") in [
        r[1:] for r in recipe_rows(fetched)
    ]


def test_building_again_leaves_the_recipes_alone(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    build(fetched, fake_claude)
    before = recipe_rows(fetched)

    summary = build(fetched, fake_claude)

    assert summary.videos == 0
    assert len(fake_claude.requests) == 5  # all from the first build
    assert recipe_rows(fetched) == before


def test_a_video_claude_couldnt_answer_about_is_left_for_the_next_build(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    """Not from the data: the error follows the shape in Anthropic's error docs."""
    error = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "x"},
    }
    fake_claude.queue.append(httpx2.Response(400, json=error))  # the first video

    summary = build(fetched, fake_claude)

    # H0tkAEL6CS8 is asked about first, and has one recipe.
    assert (summary.videos, summary.recipes) == (4, 13)
    assert list(summary.failed) == ["H0tkAEL6CS8"]
    assert build(fetched, fake_claude).videos == 1  # the next build asks again


def test_a_rejected_api_key_stops_the_build(
    fetched: Engine, fake_claude: FakeClaudeApi
) -> None:
    """Not from the data: the error follows the shape in Anthropic's error docs."""
    error = {"type": "error", "error": {"type": "authentication_error", "message": "x"}}
    fake_claude.queue.append(httpx2.Response(401, json=error))

    with pytest.raises(AIKeyError):
        build(fetched, fake_claude)
    assert len(fake_claude.requests) == 1
