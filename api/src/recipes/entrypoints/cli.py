"""The `recipes` command line. Run `recipes <playlist-id>` from `api/`."""

import argparse
import sys
from collections.abc import Sequence

from dotenv import dotenv_values, find_dotenv

from recipes.playlist import fetch_playlist
from recipes.storage import create_engine, needs_migrating, save_playlist
from recipes.youtube import YouTubeClient, YouTubeError


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line with `argv` (default: `sys.argv`). Returns the exit code."""
    parser = argparse.ArgumentParser(
        prog="recipes", description="Fetch a playlist into the database."
    )
    parser.add_argument("playlist_id", help="The ID after `list=` in its URL.")
    args = parser.parse_args(argv)

    api_key = dotenv_values(find_dotenv(usecwd=True)).get("YOUTUBE_API_KEY")
    if not api_key:
        print("error: YOUTUBE_API_KEY is not set. Add it to .env.", file=sys.stderr)
        return 1

    # Checked before fetching, so the API quota isn't spent on a fetch that can't
    # be saved.
    engine = create_engine()
    if needs_migrating(engine):
        print(
            "error: the database isn't up to date. Run `alembic upgrade head`.",
            file=sys.stderr,
        )
        return 1

    try:
        with YouTubeClient(api_key) as client:
            playlist = fetch_playlist(client, args.playlist_id)
    except YouTubeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    summary = save_playlist(playlist, engine)
    print(
        f"Saved {len(playlist.videos)} videos ({summary.added} new). "
        f"Skipped {playlist.unavailable_count} deleted or private. "
        f"Marked {summary.removed} as removed from the playlist."
    )
    return 0
