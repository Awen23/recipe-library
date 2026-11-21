"""The `recipes` command line. Run `recipes <playlist-id>` from `api/`."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dotenv import dotenv_values, find_dotenv

from recipes.playlist import fetch_playlist
from recipes.storage import save_playlist
from recipes.youtube import YouTubeClient, YouTubeError

OUTPUT = Path("data/playlist.json")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line with `argv` (default: `sys.argv`). Returns the exit code."""
    parser = argparse.ArgumentParser(
        prog="recipes", description=f"Fetch a playlist into {OUTPUT}."
    )
    parser.add_argument("playlist_id", help="The ID after `list=` in its URL.")
    args = parser.parse_args(argv)

    api_key = dotenv_values(find_dotenv(usecwd=True)).get("YOUTUBE_API_KEY")
    if not api_key:
        print("error: YOUTUBE_API_KEY is not set. Add it to .env.", file=sys.stderr)
        return 1

    try:
        with YouTubeClient(api_key) as client:
            playlist = fetch_playlist(client, args.playlist_id)
    except YouTubeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    save_playlist(playlist, OUTPUT)
    print(
        f"Saved {len(playlist.videos)} videos to {OUTPUT}. "
        f"Skipped {playlist.unavailable_count} deleted or private."
    )
    return 0
