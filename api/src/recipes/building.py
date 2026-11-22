"""Work out the recipes in fetched videos: ask Claude, split, store. Then find each
recipe's written recipe, in a linked page, the description or a creator comment.

Only videos fetched since the last build are split, and each recipe's written recipe
is only looked for once, so recipes already in use are never changed.
"""

from dataclasses import dataclass, field

from sqlalchemy import Engine

from recipes import storage
from recipes.ai import AIError, AIKeyError, Claude
from recipes.details import from_answer, links_for_claude, plain_details, readable_pages
from recipes.splitting import split_video


@dataclass
class BuildSummary:
    """What a build did."""

    videos: int = 0  # videos that got their recipes
    recipes: int = 0
    failed: dict[str, str] = field(default_factory=dict)  # video ID: why
    input_tokens: int = 0
    output_tokens: int = 0


def build_recipes(engine: Engine, claude: Claude) -> BuildSummary:
    """Split each video fetched since the last build into recipes, and store them.

    Each video's recipes are stored as soon as Claude answers, so a build that stops
    part way keeps what it did. A video Claude can't answer about is left for the next
    build to try again. A rejected API key stops the build.
    """
    summary = BuildSummary()
    for video_id, video in storage.videos_to_build(engine):
        try:
            reply = claude.find_recipes(video)
        except AIKeyError:
            raise
        except AIError as error:
            summary.failed[video_id] = str(error)
            continue
        found = split_video(video.title, video.chapters, reply.answer)
        storage.save_recipes(engine, video_id, found)
        summary.videos += 1
        summary.recipes += len(found)
        summary.input_tokens += reply.input_tokens
        summary.output_tokens += reply.output_tokens
    return summary


def fill_details(engine: Engine, claude: Claude) -> dict[str, str]:
    """Look for the written recipe of each recipe that hasn't been looked at, and
    store what's found, video by video. Returns the videos Claude couldn't answer
    about, by ID, with why: they're left for the next build. A rejected API key stops
    the build."""
    failed: dict[str, str] = {}
    # A video with links waits until they've been fetched.
    unfetched = {video_id for video_id, _ in storage.videos_to_fetch_pages(engine)}
    for video in storage.videos_to_fill(engine):
        if video.id in unfetched:
            continue
        found = plain_details(video)
        if found is None:
            pages = readable_pages(video)
            names = [recipe.name for recipe in video.recipes]
            try:
                reply = claude.find_details(video.text, names, links_for_claude(pages))
            except AIKeyError:
                raise
            except AIError as error:
                failed[video.id] = str(error)
                continue
            found = from_answer(video, pages, reply.answer)
        storage.save_details(engine, found)
    return failed
