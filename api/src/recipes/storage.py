"""Where fetched playlists are kept. All storage goes through this module.

For now that's a JSON file. In Phase 2 it becomes SQLite, and only this file changes.
"""

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import sqlalchemy
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    event,
)

from recipes.chapters import parse_chapters
from recipes.playlist import Playlist
from recipes.youtube import Video

DEFAULT_DATABASE_URL = "sqlite:///data/recipes.db"  # relative to the folder it runs in

# Every table. Alembic compares this with the database to write migrations.
metadata = MetaData(
    # Names for constraints and indexes, so a later migration can find one to change
    # or drop. SQLite would otherwise leave them unnamed. See
    # https://alembic.sqlalchemy.org/en/latest/naming.html
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

# The tables below hold what the YouTube API returned, kept as it arrived, so recipes
# can be worked out from it again without fetching. IDs are YouTube's own. Times are
# UTC. Columns are NOT NULL unless they say otherwise.

channels = Table(
    "channels",
    metadata,
    Column("id", String, primary_key=True),
    Column("title", String, nullable=False),  # updated on each fetch
)

videos = Table(
    "videos",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "channel_id",
        String,
        ForeignKey("channels.id"),
        nullable=False,
        index=True,  # for grouping by channel; SQLite doesn't index foreign keys
    ),
    Column("title", String, nullable=False),
    Column("description", Text, nullable=False),
    Column("duration_seconds", Integer, nullable=False),
    Column("published_at", DateTime, nullable=False),
    Column("thumbnail_url", String, nullable=False),
    Column("embeddable", Boolean, nullable=False),
    Column("first_seen_at", DateTime, nullable=False),
    # Set when a fetch no longer finds the video, instead of deleting it, so its
    # recipes and their ratings are kept.
    Column("removed_at", DateTime, nullable=True),
)

# Parsed from the description again on every fetch.
chapters = Table(
    "chapters",
    metadata,
    Column("video_id", String, ForeignKey("videos.id"), primary_key=True),
    Column("position", Integer, primary_key=True),  # 0, 1, 2… in description order
    Column("start_seconds", Integer, nullable=False),
    Column("title", String, nullable=False),
)

# Only the comments posted by the video's own channel.
creator_comments = Table(
    "creator_comments",
    metadata,
    Column("id", String, primary_key=True),
    Column("video_id", String, ForeignKey("videos.id"), nullable=False, index=True),
    Column("text", Text, nullable=False),
    Column("published_at", DateTime, nullable=False),
)


def create_engine(url: str | None = None) -> Engine:
    """Connect to the database at `url`, or else `DATABASE_URL`, or else the
    default. For a SQLite file, its folder is made if it's missing."""
    url = url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = sqlalchemy.create_engine(url)
    if engine.dialect.name == "sqlite":
        if engine.url.database not in (None, "", ":memory:"):
            Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
        event.listen(engine, "connect", _turn_on_foreign_keys)
    return engine


def _turn_on_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    # SQLite ignores foreign keys unless each new connection turns them on.
    # https://docs.sqlalchemy.org/en/21/dialects/sqlite.html#foreign-key-support
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def save_playlist(playlist: Playlist, path: Path) -> None:
    """Write the playlist to a JSON file."""
    data = {
        "playlist_id": playlist.id,
        "unavailable_count": playlist.unavailable_count,
        "videos": [_video_data(video) for video in playlist.videos],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def _video_data(video: Video) -> dict[str, Any]:
    """A video's fields, plus the chapters found in its description."""
    chapters = parse_chapters(video.description)
    return asdict(video) | {"chapters": [asdict(chapter) for chapter in chapters]}
