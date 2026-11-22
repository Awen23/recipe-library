from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, Table, select

from recipes.ai import Reply
from recipes.playlist import Playlist, fetch_playlist
from recipes.splitting import split_video
from recipes.storage import (
    RecipesSummary,
    SaveSummary,
    channels,
    chapters,
    create_engine,
    creator_comments,
    needs_migrating,
    recipes,
    save_answer,
    save_playlist,
    save_recipes,
    stored_answers,
    videos,
    videos_to_split,
)
from recipes.youtube import YouTubeClient

from fakes import FakeYouTubeApi, read_fixture, recorded_answer

FIRST_FETCH = datetime(2026, 11, 20, 9, 0)
SECOND_FETCH = datetime(2026, 11, 21, 9, 0)


@pytest.fixture
def playlist(fake_api: FakeYouTubeApi) -> Playlist:
    """The five real videos in the fixtures, fetched through the fake API."""
    with YouTubeClient("test-key", transport=fake_api.transport) as client:
        return fetch_playlist(client, "PLAYLIST_ID")


def rows(engine: Engine, table: Table) -> list[dict[str, Any]]:
    """Every row in the table, as a dict of column name to value."""
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(table)).mappings()]


def row(engine: Engine, table: Table, **where: Any) -> dict[str, Any]:
    """The one row whose columns have these values."""
    [match] = [r for r in rows(engine, table) if r.items() >= where.items()]
    return match


def test_save_stores_each_video(engine: Engine, playlist: Playlist) -> None:
    save_playlist(playlist, engine, now=FIRST_FETCH)

    assert {r["id"] for r in rows(engine, videos)} == {v.id for v in playlist.videos}
    assert row(engine, videos, id="whr7iOKRXTA") == {
        "id": "whr7iOKRXTA",
        "channel_id": "UCS_S4EpORZwt8x9r6Mvjs7Q",
        "title": "Plant-based meal prep for the week (SUPER tasty vegan recipes) 🥯",
        "description": "Hi friends, welcome back to another meal prep video!! This "
        "one was arguably my best meal prep yet, and I hope you enjoy ☺️",
        "duration_seconds": 1157,
        "published_at": datetime(2025, 6, 17, 8, 39, 43),  # "2025-06-17T08:39:43Z"
        "thumbnail_url": "https://i.ytimg.com/vi/whr7iOKRXTA/mqdefault.jpg",
        "embeddable": True,
        "first_seen_at": FIRST_FETCH,
        "removed_at": None,
    }


def test_save_stores_each_channel_once(engine: Engine, playlist: Playlist) -> None:
    save_playlist(playlist, engine)

    # The five videos are by five different channels.
    assert len(rows(engine, channels)) == 5
    assert row(engine, channels, id="UCS_S4EpORZwt8x9r6Mvjs7Q") == {
        "id": "UCS_S4EpORZwt8x9r6Mvjs7Q",
        "title": "Amanda Ducks",
    }


def test_save_stores_the_creator_comments(engine: Engine, playlist: Playlist) -> None:
    save_playlist(playlist, engine)

    [comment] = rows(engine, creator_comments)
    assert comment["id"] == "Ugwnsgb1qinFFq2Wf3B4AaABAg"
    assert comment["video_id"] == "eG0tXlljTtI"
    assert comment["text"].startswith("I feel guilty of using a lot of plastic wrap")
    assert comment["published_at"] == datetime(2022, 8, 28, 7, 8, 42)


def test_save_stores_the_chapters_in_order(engine: Engine, playlist: Playlist) -> None:
    # videos.json has trimmed descriptions, so use the full one with its timestamps.
    description = read_fixture("descriptions.json")["whr7iOKRXTA"]
    [first, *rest] = playlist.videos
    with_chapters = replace(first, description=description)

    save_playlist(replace(playlist, videos=(with_chapters, *rest)), engine)

    saved = [r for r in rows(engine, chapters) if r["video_id"] == "whr7iOKRXTA"]
    assert [(r["position"], r["start_seconds"], r["title"]) for r in saved[:2]] == [
        (0, 0, "Intro"),
        (1, 102, "Breakfasts"),
    ]
    assert len(saved) == 6


def test_saving_again_leaves_stored_videos_alone(
    engine: Engine, playlist: Playlist
) -> None:
    save_playlist(playlist, engine, now=FIRST_FETCH)
    # Not from the data: the creator edits the title and description, and the
    # channel is renamed.
    [first, *rest] = playlist.videos
    edited = replace(
        first,
        title="Edited title",
        description=read_fixture("descriptions.json")["whr7iOKRXTA"],
        channel_title="Renamed channel",
    )

    summary = save_playlist(
        replace(playlist, videos=(edited, *rest)), engine, now=SECOND_FETCH
    )

    assert summary == SaveSummary(added=0, removed=0)
    video = row(engine, videos, id="whr7iOKRXTA")
    assert video["title"] == first.title
    assert video["first_seen_at"] == FIRST_FETCH
    assert row(engine, channels, id=first.channel_id)["title"] == "Amanda Ducks"
    # The new description has chapters, but the stored video's are kept as they were.
    assert rows(engine, chapters) == []
    assert len(rows(engine, videos)) == 5
    assert len(rows(engine, creator_comments)) == 1


def test_a_video_that_leaves_is_marked_removed_not_deleted(
    engine: Engine, playlist: Playlist
) -> None:
    first_save = save_playlist(playlist, engine, now=FIRST_FETCH)
    without_first = replace(playlist, videos=playlist.videos[1:])

    second_save = save_playlist(without_first, engine, now=SECOND_FETCH)

    assert first_save == SaveSummary(added=5, removed=0)
    assert second_save == SaveSummary(added=0, removed=1)
    assert row(engine, videos, id="whr7iOKRXTA")["removed_at"] == SECOND_FETCH
    assert row(engine, videos, id="nHr9LqK3PKc")["removed_at"] is None


def test_a_video_that_comes_back_is_no_longer_removed(
    engine: Engine, playlist: Playlist
) -> None:
    save_playlist(playlist, engine, now=FIRST_FETCH)
    save_playlist(replace(playlist, videos=playlist.videos[1:]), engine)

    save_playlist(playlist, engine)

    video = row(engine, videos, id="whr7iOKRXTA")
    assert video["removed_at"] is None
    assert video["first_seen_at"] == FIRST_FETCH


def test_needs_migrating_until_every_migration_has_run(
    alembic_config: Config,
) -> None:
    engine = create_engine()
    assert needs_migrating(engine)  # a new database: none have run

    command.upgrade(alembic_config, "head")
    assert not needs_migrating(engine)

    # One step back is what a database looks like after you pull a new migration.
    command.downgrade(alembic_config, "-1")
    assert needs_migrating(engine)


def test_create_engine_makes_the_database_and_its_folder(tmp_path: Path) -> None:
    path = tmp_path / "data" / "recipes.db"

    with create_engine(f"sqlite:///{path}").connect():
        pass

    assert path.exists()


def test_create_engine_turns_on_foreign_keys(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'recipes.db'}")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_create_engine_uses_database_url_when_none_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'other.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    assert create_engine().url.database == str(tmp_path / "other.db")


@pytest.fixture
def saved(engine: Engine, playlist: Playlist) -> Engine:
    """The playlist saved, with the full descriptions of the videos that have them,
    so their chapters are stored too."""
    descriptions = read_fixture("descriptions.json")
    full = tuple(
        replace(video, description=descriptions.get(video.id, video.description))
        for video in playlist.videos
    )
    save_playlist(replace(playlist, videos=full), engine, now=FIRST_FETCH)
    return engine


def whr7_recipes(engine: Engine) -> list[dict[str, Any]]:
    return sorted(
        (r for r in rows(engine, recipes) if r["video_id"] == "whr7iOKRXTA"),
        key=lambda r: r["position"],
    )


def save_whr7_recipes(engine: Engine, **kwargs: Any) -> RecipesSummary:
    [(_, video)] = [v for v in videos_to_split(engine) if v[0] == "whr7iOKRXTA"]
    found = split_video(video.title, video.chapters, recorded_answer("whr7iOKRXTA"))
    return save_recipes(engine, "whr7iOKRXTA", found, **kwargs)


def test_videos_to_split_have_their_chapters_and_creator_comments(
    saved: Engine,
) -> None:
    to_split = dict(videos_to_split(saved))

    assert len(to_split) == 5
    assert [c.title for c in to_split["whr7iOKRXTA"].chapters][:2] == [
        "Intro",
        "Breakfasts",
    ]
    [comment] = to_split["eG0tXlljTtI"].creator_comments
    assert comment.startswith("I feel guilty of using a lot of plastic wrap")


def test_a_stored_answer_is_found_again(saved: Engine) -> None:
    reply = Reply(recorded_answer("whr7iOKRXTA"), "end_turn", 3310, 206)

    save_answer(saved, "whr7iOKRXTA", reply)

    assert stored_answers(saved) == {"whr7iOKRXTA": reply.answer}


def test_save_recipes_stores_each_recipe(saved: Engine) -> None:
    summary = save_whr7_recipes(saved)

    assert summary == RecipesSummary(added=5, removed=0)
    first = whr7_recipes(saved)[0]
    assert {k: first[k] for k in ("position", "chapter_position", "name")} == {
        "position": 0,
        "chapter_position": 1,
        "name": "Overnight oats",
    }
    assert (first["start_seconds"], first["start_by"]) == (102, "ai")


def test_saving_recipes_again_keeps_their_ids(saved: Engine) -> None:
    save_whr7_recipes(saved)
    ids = [r["id"] for r in whr7_recipes(saved)]

    summary = save_whr7_recipes(saved)

    assert summary == RecipesSummary(added=0, removed=0)
    assert [r["id"] for r in whr7_recipes(saved)] == ids


def test_saving_recipes_keeps_fields_set_by_hand(saved: Engine) -> None:
    """Not from the data: nothing sets fields by hand yet, so one is set here."""
    save_whr7_recipes(saved)
    with saved.begin() as connection:
        connection.execute(
            recipes.update()
            .where(recipes.c.video_id == "whr7iOKRXTA", recipes.c.position == 0)
            .values(name="Three breakfasts", name_by="hand")
        )

    save_whr7_recipes(saved)

    first, second = whr7_recipes(saved)[:2]
    assert (first["name"], first["name_by"]) == ("Three breakfasts", "hand")
    assert first["start_seconds"] == 102  # not set by hand, so still updated
    assert second["name"] == "Mexican inspired salad"


def test_recipes_past_the_last_one_found_are_marked_as_removed(
    saved: Engine,
) -> None:
    """Not from the data: Claude's answer is cut down to two recipes."""
    save_whr7_recipes(saved)
    [(_, video)] = [v for v in videos_to_split(saved) if v[0] == "whr7iOKRXTA"]
    found = split_video(video.title, video.chapters, recorded_answer("whr7iOKRXTA"))

    summary = save_recipes(saved, "whr7iOKRXTA", found[:2], now=SECOND_FETCH)

    assert summary == RecipesSummary(added=0, removed=3)
    assert [r["removed_at"] for r in whr7_recipes(saved)] == [None, None] + [
        SECOND_FETCH
    ] * 3
