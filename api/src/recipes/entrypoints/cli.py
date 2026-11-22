"""The `recipes` command line. Run `recipes --help` from `api/` for its commands."""

import argparse
import sys
from collections.abc import Sequence

from dotenv import dotenv_values, find_dotenv
from sqlalchemy import Engine

from recipes import storage
from recipes.ai import AIKeyError, Claude
from recipes.building import build_recipes
from recipes.playlist import fetch_playlist
from recipes.youtube import YouTubeClient, YouTubeError


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line with `argv` (default: `sys.argv`). Returns the exit code."""
    parser = argparse.ArgumentParser(prog="recipes")
    commands = parser.add_subparsers(required=True, metavar="command")

    fetch = commands.add_parser(
        "fetch", help="fetch a playlist's new videos into the database"
    )
    fetch.add_argument("playlist_id", help="the ID after `list=` in its URL")
    fetch.set_defaults(run=_fetch)

    build = commands.add_parser(
        "build", help="split new videos into recipes, asking Claude"
    )
    build.set_defaults(run=_build)

    args = parser.parse_args(argv)
    return args.run(args)


def _fetch(args: argparse.Namespace) -> int:
    api_key = _secret("YOUTUBE_API_KEY")
    if not api_key:
        return 1

    # Checked before fetching, so the API quota isn't spent on a fetch that can't
    # be saved.
    engine = _open_database()
    if engine is None:
        return 1

    try:
        with YouTubeClient(api_key) as client:
            playlist = fetch_playlist(client, args.playlist_id)
    except YouTubeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    summary = storage.save_playlist(playlist, engine)
    print(
        f"Saved {len(playlist.videos)} videos ({summary.added} new). "
        f"Skipped {playlist.unavailable_count} deleted or private. "
        f"Marked {summary.removed} as removed from the playlist."
    )
    return 0


def _build(_args: argparse.Namespace) -> int:
    engine = _open_database()
    api_key = _secret("ANTHROPIC_API_KEY")
    if engine is None or not api_key:
        return 1

    try:
        with Claude(api_key) as claude:
            summary = build_recipes(engine, claude)
    except AIKeyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(
        f"Built {summary.recipes} recipes from {summary.videos} new videos "
        f"({summary.input_tokens} input and {summary.output_tokens} output tokens)."
    )
    for video_id, reason in summary.failed.items():
        print(
            f"error: {video_id}: {reason}. Run `recipes build` again.", file=sys.stderr
        )
    return 1 if summary.failed else 0


def _secret(name: str) -> str | None:
    """A key from .env, or None after saying how to set it."""
    value = dotenv_values(find_dotenv(usecwd=True)).get(name)
    if not value:
        print(f"error: {name} is not set. Add it to .env.", file=sys.stderr)
    return value or None


def _open_database() -> Engine | None:
    """The database, or None after saying how to bring it up to date."""
    engine = storage.create_engine()
    if storage.needs_migrating(engine):
        print(
            "error: the database isn't up to date. Run `alembic upgrade head`.",
            file=sys.stderr,
        )
        return None
    return engine
