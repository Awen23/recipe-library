"""Where fetched videos and pages, and the recipes worked out from them, are kept.
All database access goes through this module.

The database is SQLite, at `data/recipes.db` unless `DATABASE_URL` says otherwise.
Its tables are created by the migrations in `migrations/`: run `alembic upgrade head`.
"""

import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import sqlalchemy
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Engine,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from recipes.ai import VideoText
from recipes.chapters import Chapter, parse_chapters
from recipes.links import Link, find_links
from recipes.models import (
    Details,
    Interest,
    Line,
    Marks,
    RecipeName,
    StoredPage,
    Verdict,
    VideoToFill,
)
from recipes.pages import Page
from recipes.playlist import Playlist
from recipes.recipe_data import PageRecipe
from recipes.splitting import Recipe
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

# JSON that stores None as SQL NULL, not as the JSON text "null", so `IS NULL` finds
# it.
_JSON = JSON(none_as_null=True)

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

# One row per link in a video's description or creator comments that may lead to a
# written recipe (`links.find_links`), with what fetching it found. A video's links
# are fetched once.
recipe_links = Table(
    "recipe_links",
    metadata,
    Column("video_id", String, ForeignKey("videos.id"), primary_key=True),
    Column("url", String, primary_key=True),  # as written in the video
    Column("position", Integer, nullable=False),  # 0, 1, 2… in the order written
    Column("link_text", String, nullable=False),  # the words on the link's line
    Column("final_url", String, nullable=True),  # after redirects, if it answered
    Column("fetched_at", DateTime, nullable=False),
    Column("outcome", String, nullable=False),  # see `pages`, such as "recipe"
    # The page's first recipe, {"name", "ingredients", "method"}, when it has one.
    Column("recipe", _JSON, nullable=True),
    # The page's text, when it has no recipe data, for Claude to read the recipe from.
    # Only its text, without the page's markup or scripts.
    Column("page_text", Text, nullable=True),
)


# Who set a group of recipe fields: plain code, AI, or a correction by hand.
SET_BY = ("code", "ai", "hand")
# Where a recipe's written recipe was found.
SOURCES = ("link", "description", "comment")


def _one_of(column: str, allowed: Sequence[str]) -> CheckConstraint:
    values = ", ".join(f"'{value}'" for value in allowed)
    return CheckConstraint(f"{column} IN ({values})", name=column)


def _set_by(column: str) -> CheckConstraint:
    return _one_of(column, SET_BY)


# The tables below are worked out from the fetched ones, by code and by AI.

# One row per recipe. A video has one or more, in the order they appear in it. Rows
# are only ever added, so ratings and corrections stay attached. A recipe whose video
# has left the playlist is removed along with it (`videos.removed_at`).
recipes = Table(
    "recipes",
    metadata,
    # Never reused, even after a row is deleted, so links to a recipe stay right.
    Column("id", Integer, primary_key=True),
    Column("video_id", String, ForeignKey("videos.id"), nullable=False),
    Column("position", Integer, nullable=False),  # 0, 1, 2… within the video
    # The chapter the recipe starts in, if the video has chapters.
    Column("chapter_position", Integer, nullable=True),
    Column("name", String, nullable=False),
    Column("name_by", String, nullable=False),
    Column("name_confidence", Integer, nullable=True),  # 0-100, when AI named it
    # Where the recipe starts in the video. Null when it isn't known.
    Column("start_seconds", Integer, nullable=True),
    Column("start_by", String, nullable=False),
    # The written recipe, and where it came from. A build looks for them once, and
    # `details_by` says who looked. The rest stay null when nothing was found.
    # Lists of `models.Line`: {"text": "1 cup oats", "note": false}.
    Column("ingredients", _JSON, nullable=True),
    Column("method", _JSON, nullable=True),
    Column("source", String, nullable=True),  # "link", "description" or "comment"
    Column("source_url", String, nullable=True),  # the page, when it's from a link
    Column("details_by", String, nullable=True),
    Column("details_confidence", Integer, nullable=True),  # 0-100, how sure
    UniqueConstraint("video_id", "position"),
    ForeignKeyConstraint(
        ["video_id", "chapter_position"], ["chapters.video_id", "chapters.position"]
    ),
    _set_by("name_by"),
    _set_by("start_by"),
    _set_by("details_by"),
    _one_of("source", SOURCES),
    sqlite_autoincrement=True,  # what keeps `id`s from being reused
)

# The levels of each mark, from the types in `models`.
INTERESTS = get_args(Interest)
VERDICTS = get_args(Verdict)

# My own marks on recipes, set by hand: one row per recipe I've marked. Building
# never reads or writes this table, so the marks survive it. A recipe with no row
# has no marks, and is shown.
recipe_marks = Table(
    "recipe_marks",
    metadata,
    Column("recipe_id", Integer, ForeignKey("recipes.id"), primary_key=True),
    # Before cooking it: one of INTERESTS, or null if I haven't decided.
    # "not_for_me" hides the recipe.
    Column("interest", String, nullable=True),
    # After cooking it: one of VERDICTS, or null if I haven't cooked it.
    Column("verdict", String, nullable=True),
    Column("updated_at", DateTime, nullable=False),
    _one_of("interest", INTERESTS),
    _one_of("verdict", VERDICTS),
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


def videos_to_build(engine: Engine) -> list[tuple[str, VideoText]]:
    """The videos fetched since the last build, by ID, with what Claude is shown
    about each. They're the ones with no recipes, since building gives every video
    at least one."""
    with engine.connect() as connection:
        video_ids = list(
            connection.scalars(
                select(videos.c.id)
                .where(
                    videos.c.removed_at.is_(None),
                    videos.c.id.not_in(select(recipes.c.video_id)),
                )
                .order_by(videos.c.first_seen_at, videos.c.id)
            )
        )
        texts = _video_texts(connection, video_ids)
    return [(video_id, texts[video_id]) for video_id in video_ids]


def _video_texts(
    connection: sqlalchemy.Connection, video_ids: Sequence[str]
) -> dict[str, VideoText]:
    """What Claude is shown about each video, by ID."""
    chapters_by_video: dict[str, list[Chapter]] = {}
    for chapter in connection.execute(
        select(chapters)
        .where(chapters.c.video_id.in_(video_ids))
        .order_by(chapters.c.video_id, chapters.c.position)
    ):
        chapters_by_video.setdefault(chapter.video_id, []).append(
            Chapter(chapter.start_seconds, chapter.title)
        )
    comments_by_video: dict[str, list[str]] = {}
    for comment in connection.execute(
        select(creator_comments)
        .where(creator_comments.c.video_id.in_(video_ids))
        .order_by(creator_comments.c.published_at)
    ):
        comments_by_video.setdefault(comment.video_id, []).append(comment.text)
    return {
        row.id: VideoText(
            title=row.title,
            description=row.description,
            chapters=chapters_by_video.get(row.id, []),
            creator_comments=comments_by_video.get(row.id, []),
        )
        for row in connection.execute(
            select(videos.c.id, videos.c.title, videos.c.description).where(
                videos.c.id.in_(video_ids)
            )
        )
    }


def save_recipes(engine: Engine, video_id: str, found: Sequence[Recipe]) -> None:
    """Store a video's recipes, in one transaction."""
    with engine.begin() as connection:
        _insert(
            connection,
            recipes,
            [
                {
                    "video_id": video_id,
                    "position": recipe.position,
                    "chapter_position": recipe.chapter_position,
                    "name": recipe.name,
                    "name_by": recipe.name_by,
                    "name_confidence": recipe.name_confidence,
                    "start_seconds": recipe.start_seconds,
                    "start_by": recipe.start_by,
                }
                for recipe in found
            ],
        )


def videos_to_fetch_pages(engine: Engine) -> list[tuple[str, list[Link]]]:
    """The live videos whose links haven't been fetched yet, by ID, with their links.
    Videos with no links are left out."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(videos.c.id, videos.c.description)
            .where(
                videos.c.removed_at.is_(None),
                videos.c.id.not_in(select(recipe_links.c.video_id)),
            )
            .order_by(videos.c.first_seen_at, videos.c.id)
        ).all()
        comments_by_video: dict[str, list[str]] = {}
        for comment in connection.execute(
            select(creator_comments).order_by(creator_comments.c.published_at)
        ):
            comments_by_video.setdefault(comment.video_id, []).append(comment.text)
    found = [
        (row.id, find_links(row.description, comments_by_video.get(row.id, [])))
        for row in rows
    ]
    return [(video_id, links) for video_id, links in found if links]


def save_pages(
    engine: Engine,
    video_id: str,
    fetched: Sequence[tuple[Link, Page]],
    *,
    now: datetime | None = None,
) -> None:
    """Store what fetching each of a video's links found, in one transaction."""
    now = now or _utc_now()
    with engine.begin() as connection:
        _insert(
            connection,
            recipe_links,
            [
                {
                    "video_id": video_id,
                    "url": link.url,
                    "position": position,
                    "link_text": link.text,
                    "final_url": page.final_url,
                    "fetched_at": now,
                    "outcome": page.outcome,
                    "recipe": asdict(page.recipe) if page.recipe else None,
                    "page_text": page.text,
                }
                for position, (link, page) in enumerate(fetched)
            ],
        )


def videos_to_fill(engine: Engine) -> list[VideoToFill]:
    """The live videos with a recipe whose details haven't been looked for."""
    with engine.connect() as connection:
        video_ids = list(
            connection.scalars(
                select(recipes.c.video_id)
                .distinct()
                .join(videos, videos.c.id == recipes.c.video_id)
                .where(recipes.c.details_by.is_(None), videos.c.removed_at.is_(None))
                .order_by(recipes.c.video_id)
            )
        )
        texts = _video_texts(connection, video_ids)
        result = []
        for video_id in video_ids:
            rows = connection.execute(
                select(recipes.c.id, recipes.c.name, recipes.c.details_by)
                .where(recipes.c.video_id == video_id)
                .order_by(recipes.c.position)
            ).all()
            pages = connection.execute(
                select(recipe_links)
                .where(recipe_links.c.video_id == video_id)
                .order_by(recipe_links.c.position)
            ).all()
            result.append(
                VideoToFill(
                    id=video_id,
                    text=texts[video_id],
                    recipes=[RecipeName(row.id, row.name) for row in rows],
                    to_fill={row.id for row in rows if row.details_by is None},
                    pages=[
                        StoredPage(
                            url=page.final_url or page.url,
                            link_text=page.link_text,
                            outcome=page.outcome,
                            recipe=PageRecipe(**page.recipe) if page.recipe else None,
                            text=page.page_text,
                        )
                        for page in pages
                    ],
                )
            )
    return result


def save_details(engine: Engine, found: dict[int, Details]) -> None:
    """Store what was found for each recipe, by ID, in one transaction. A recipe
    whose details have already been looked for is left as it is."""
    with engine.begin() as connection:
        for recipe_id, details in found.items():
            connection.execute(
                update(recipes)
                .where(recipes.c.id == recipe_id, recipes.c.details_by.is_(None))
                .values(
                    ingredients=_lines(details.ingredients),
                    method=_lines(details.method),
                    source=details.source,
                    source_url=details.source_url,
                    details_by=details.by,
                    details_confidence=details.confidence,
                )
            )


class NoSuchRecipeError(LookupError):
    """There's no recipe with this ID."""


def set_interest(
    engine: Engine,
    recipe_id: int,
    interest: Interest | None,
    *,
    now: datetime | None = None,
) -> Marks:
    """Set how interested I am in a recipe, or clear it with None. Returns its
    marks."""
    return _mark(engine, recipe_id, {"interest": interest}, now or _utc_now())


def set_verdict(
    engine: Engine,
    recipe_id: int,
    verdict: Verdict | None,
    *,
    now: datetime | None = None,
) -> Marks:
    """Set what I thought of a recipe after cooking it, or clear it with None.
    Returns its marks."""
    return _mark(engine, recipe_id, {"verdict": verdict}, now or _utc_now())


def _mark(
    engine: Engine, recipe_id: int, changes: dict[str, Any], now: datetime
) -> Marks:
    """Change some of a recipe's marks and leave the rest, adding its row if it has
    none yet: one "upsert", which SQLite and Postgres both write as
    `INSERT ... ON CONFLICT DO UPDATE`. Moving to Postgres swaps `sqlite_insert` for
    the same function from `sqlalchemy.dialects.postgresql`. See
    https://docs.sqlalchemy.org/en/21/dialects/sqlite.html#insert-on-conflict-upsert
    """
    with engine.begin() as connection:
        found = connection.scalar(select(recipes.c.id).where(recipes.c.id == recipe_id))
        if found is None:
            raise NoSuchRecipeError(recipe_id)
        new_row = {"recipe_id": recipe_id, "interest": None, "verdict": None}
        statement = sqlite_insert(recipe_marks).values(
            {**new_row, **changes, "updated_at": now}
        )
        row = connection.execute(
            statement.on_conflict_do_update(
                index_elements=[recipe_marks.c.recipe_id],
                set_={**changes, "updated_at": now},
            ).returning(
                recipe_marks.c.interest,
                recipe_marks.c.verdict,
                recipe_marks.c.updated_at,
            )
        ).one()
    return Marks(row.interest, row.verdict, row.updated_at)


def _lines(lines: Sequence[Line] | None) -> list[dict[str, Any]] | None:
    return None if lines is None else [asdict(line) for line in lines]


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
