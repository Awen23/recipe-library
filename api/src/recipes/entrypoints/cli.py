"""The `recipes` command line. Run `recipes --help` from `api/` for its commands."""

import argparse
import sys
from collections.abc import Sequence

from dotenv import dotenv_values, find_dotenv
from sqlalchemy import Engine

from recipes import storage
from recipes.ai import AIError, AIKeyError, Claude, VideoAnswer, VideoText
from recipes.playlist import fetch_playlist
from recipes.splitting import split_video
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
        "build", help="work out the recipes in the fetched videos, asking Claude"
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
    if engine is None:
        return 1

    videos = storage.videos_to_split(engine)
    answers = storage.stored_answers(engine)
    to_ask = [(id_, video) for id_, video in videos if id_ not in answers]

    asked = input_tokens = output_tokens = 0
    if to_ask:
        api_key = _secret("ANTHROPIC_API_KEY")
        if api_key:
            print(f"Asking Claude about {len(to_ask)} videos…")
            asked, input_tokens, output_tokens = _ask_claude(
                engine, api_key, to_ask, answers
            )
    failed = len(to_ask) - asked

    added = removed = total = 0
    for video_id, video in videos:
        if video_id not in answers:
            continue  # asking failed; its stored recipes are left as they are
        found = split_video(video.title, video.chapters, answers[video_id])
        summary = storage.save_recipes(engine, video_id, found)
        added, removed = added + summary.added, removed + summary.removed
        total += len(found)
    # Videos that left the playlist aren't split again; their recipes go with them.
    removed += storage.remove_recipes_of_removed_videos(engine)

    print(
        f"Built {total} recipes from {len(videos) - failed} videos "
        f"({added} new, {removed} marked as removed). "
        f"Asked Claude about {asked} videos "
        f"({input_tokens} input and {output_tokens} output tokens)."
    )
    if failed:
        print(
            f"error: {failed} videos have no answer from Claude yet. "
            "Run `recipes build` again to retry them.",
            file=sys.stderr,
        )
        return 1
    return 0


def _ask_claude(
    engine: Engine,
    api_key: str,
    to_ask: list[tuple[str, VideoText]],
    answers: dict[str, VideoAnswer | None],
) -> tuple[int, int, int]:
    """Ask Claude about each video, adding the answers to `answers`. Returns how
    many were answered, and the input and output tokens used.

    Each answer is stored as it arrives, so a build that stops part way doesn't
    pay for the same answers again.
    """
    asked = input_tokens = output_tokens = 0
    with Claude(api_key) as claude:
        for video_id, video in to_ask:
            try:
                reply = claude.find_recipes(video)
            except AIKeyError as error:
                print(f"error: {error}", file=sys.stderr)
                break  # every later request would be rejected too
            except AIError as error:
                print(f"warning: {video_id}: {error}", file=sys.stderr)
                continue
            storage.save_answer(engine, video_id, reply)
            answers[video_id] = reply.answer
            asked += 1
            input_tokens += reply.input_tokens
            output_tokens += reply.output_tokens
    return asked, input_tokens, output_tokens


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
