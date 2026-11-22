import json
from dataclasses import replace
from pathlib import Path

import pytest

from recipes.playlist import Playlist
from recipes.storage import create_engine, save_playlist
from recipes.youtube import Video

from fakes import read_fixture


def video(video_id: str) -> Video:
    """One real video from the fixtures."""
    [item] = [i for i in read_fixture("videos.json")["items"] if i["id"] == video_id]
    return Video.from_api(item)


def test_save_writes_the_playlist_as_json(tmp_path: Path) -> None:
    # tmp_path starts empty, so save_playlist has to create the data/ folder itself.
    path = tmp_path / "data" / "playlist.json"

    save_playlist(Playlist("PLAYLIST_ID", (video("whr7iOKRXTA"),), 2, {}), path)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "playlist_id": "PLAYLIST_ID",
        "unavailable_count": 2,
        "videos": [
            {
                "id": "whr7iOKRXTA",
                "title": "Plant-based meal prep for the week "
                "(SUPER tasty vegan recipes) 🥯",
                "description": "Hi friends, welcome back to another meal prep "
                "video!! This one was arguably my best meal prep yet, and I hope "
                "you enjoy ☺️",
                "duration_seconds": 1157,
                "published_at": "2025-06-17T08:39:43Z",
                "channel_id": "UCS_S4EpORZwt8x9r6Mvjs7Q",
                "channel_title": "Amanda Ducks",
                "thumbnail_url": "https://i.ytimg.com/vi/whr7iOKRXTA/mqdefault.jpg",
                "embeddable": True,
                "chapters": [],
            }
        ],
    }


def test_save_includes_the_chapters_in_each_description(tmp_path: Path) -> None:
    # videos.json has trimmed descriptions, so use the full one with its timestamps.
    description = read_fixture("descriptions.json")["whr7iOKRXTA"]
    with_chapters = replace(video("whr7iOKRXTA"), description=description)
    path = tmp_path / "playlist.json"

    save_playlist(Playlist("PLAYLIST_ID", (with_chapters,), 0, {}), path)

    [saved] = json.loads(path.read_text(encoding="utf-8"))["videos"]
    assert saved["chapters"][:2] == [
        {"start_seconds": 0, "title": "Intro"},
        {"start_seconds": 102, "title": "Breakfasts"},
    ]
    assert len(saved["chapters"]) == 6


def test_save_keeps_non_english_text_readable(tmp_path: Path) -> None:
    path = tmp_path / "playlist.json"

    save_playlist(Playlist("PLAYLIST_ID", (video("eG0tXlljTtI"),), 0, {}), path)

    # The Japanese in this title is written as real characters, not as escape codes
    # (a backslash, "u" and four hex digits), so the file stays readable.
    assert "ヴィーガン" in path.read_text(encoding="utf-8")


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
