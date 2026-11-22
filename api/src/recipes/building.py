"""Work out the recipes in fetched videos: ask Claude, split, store.

Only videos fetched since the last build are built, so recipes already in use are
never changed.
"""

from dataclasses import dataclass, field

from sqlalchemy import Engine

from recipes import storage
from recipes.ai import AIError, AIKeyError, Claude
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
