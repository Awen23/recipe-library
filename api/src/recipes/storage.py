"""Where fetched playlists are kept. All database access goes through this module.

The database is SQLite, at `data/recipes.db` unless `DATABASE_URL` says otherwise.
Its tables are created by the migrations in `migrations/`: run `alembic upgrade head`.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
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
    insert,
    select,
    update,
)

from recipes.chapters import parse_chapters
from recipes.playlist import Playlist
from recipes.youtube import Comment, Video

DEFAULT_DATABASE_URL = "sqlite:///data/recipes.db"  # relative to the folder it runs in
PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"  # holds Alembic's settings

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
    Column("title", String, nullable=False),
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

# Parsed from the description when the video is first stored.
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


def needs_migrating(engine: Engine) -> bool:
    """Whether the database is missing any of the migrations in `migrations/`."""
    newest = ScriptDirectory.from_config(Config(toml_file=PYPROJECT)).get_heads()
    with engine.connect() as connection:
        # Read from the `alembic_version` table, which is empty before any have run.
        current = MigrationContext.configure(connection).get_current_heads()
    return set(current) != set(newest)


@dataclass(frozen=True)
class SaveSummary:
    """What changed in the database when a playlist was saved."""

    added: int  # videos stored for the first time
    removed: int  # videos marked as removed, because the playlist no longer has them


def save_playlist(
    playlist: Playlist, engine: Engine, *, now: datetime | None = None
) -> SaveSummary:
    """Store the videos that are new to the database, with their channels, chapters
    and creator comments, and mark the stored videos that have left the playlist.

    Stored videos are otherwise left as they are. It all happens in one transaction.
    `now` is when this fetch happened.
    """
    now = now or _utc_now()
    in_playlist = [video.id for video in playlist.videos]
    with engine.begin() as connection:
        stored_videos = set(connection.scalars(select(videos.c.id)))
        stored_channels = set(connection.scalars(select(channels.c.id)))
        new = [video for video in playlist.videos if video.id not in stored_videos]

        # A dict, so a channel with several new videos is only added once.
        new_channels = {
            video.channel_id: video.channel_title
            for video in new
            if video.channel_id not in stored_channels
        }
        _insert(
            connection,
            channels,
            [{"id": id_, "title": title} for id_, title in new_channels.items()],
        )
        _insert(connection, videos, [_video_row(video, now) for video in new])
        _insert(connection, chapters, [r for v in new for r in _chapter_rows(v)])
        _insert(
            connection,
            creator_comments,
            [
                _comment_row(comment, video.id)
                for video in new
                for comment in playlist.creator_comments.get(video.id, ())
            ],
        )

        removed = connection.execute(
            update(videos)
            .where(videos.c.id.not_in(in_playlist), videos.c.removed_at.is_(None))
            .values(removed_at=now)
        ).rowcount
        # A video that was removed and is back in the playlist isn't removed any more.
        connection.execute(
            update(videos)
            .where(videos.c.id.in_(in_playlist), videos.c.removed_at.is_not(None))
            .values(removed_at=None)
        )

    return SaveSummary(added=len(new), removed=removed)


def _insert(
    connection: sqlalchemy.Connection, table: Table, rows: Sequence[dict[str, Any]]
) -> None:
    if rows:  # SQLAlchemy needs at least one row to insert
        connection.execute(insert(table), rows)


def _video_row(video: Video, now: datetime) -> dict[str, Any]:
    return {
        "id": video.id,
        "channel_id": video.channel_id,
        "title": video.title,
        "description": video.description,
        "duration_seconds": video.duration_seconds,
        "published_at": _utc(video.published_at),
        "thumbnail_url": video.thumbnail_url,
        "embeddable": video.embeddable,
        "first_seen_at": now,
        "removed_at": None,
    }


def _chapter_rows(video: Video) -> list[dict[str, Any]]:
    return [
        {
            "video_id": video.id,
            "position": position,
            "start_seconds": chapter.start_seconds,
            "title": chapter.title,
        }
        for position, chapter in enumerate(parse_chapters(video.description))
    ]


def _comment_row(comment: Comment, video_id: str) -> dict[str, Any]:
    return {
        "id": comment.id,
        "video_id": video_id,
        "text": comment.text,
        "published_at": _utc(comment.published_at),
    }


def _utc(timestamp: str) -> datetime:
    """Turn a YouTube time such as `2022-08-27T14:00:17Z` into a UTC datetime.

    The datetime has no time zone attached, because SQLite can't store one. Every
    time in the database is UTC.
    """
    return datetime.fromisoformat(timestamp).astimezone(UTC).replace(tzinfo=None)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
