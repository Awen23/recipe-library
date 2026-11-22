"""Split a video into its recipes, from its chapters and Claude's answer.

Every video gets at least one recipe, so each video in the library can be found.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from recipes.ai import VideoAnswer
from recipes.chapters import Chapter


@dataclass(frozen=True)
class Recipe:
    """One recipe's fields, as code and AI set them. `_by` says which did."""

    position: int  # 0, 1, 2… within the video
    chapter_position: int | None
    name: str
    name_by: str
    name_confidence: int | None
    start_seconds: int | None
    start_by: str


def split_video(
    title: str, chapters: Sequence[Chapter], answer: VideoAnswer | None
) -> list[Recipe]:
    """The recipes in a video, in order.

    With Claude's answer, each recipe it found is one, named by Claude. A recipe
    starts where its chapter starts, unless an earlier recipe already starts there:
    when one chapter holds several recipes, only the first one's start is known.
    Without an answer, each chapter is a recipe named after the chapter. A video
    with no recipes found is one recipe, named after the video.
    """
    if answer is not None and answer.recipes:
        return _from_answer(answer, chapters)
    if answer is None and chapters:
        return [
            Recipe(
                position=position,
                chapter_position=position,
                name=chapter.title,
                name_by="code",
                name_confidence=None,
                start_seconds=chapter.start_seconds,
                start_by="code",
            )
            for position, chapter in enumerate(chapters)
        ]
    return [
        Recipe(
            position=0,
            chapter_position=None,
            name=title,
            name_by="code",
            name_confidence=None,
            start_seconds=None,
            start_by="code",
        )
    ]


def _from_answer(answer: VideoAnswer, chapters: Sequence[Chapter]) -> list[Recipe]:
    recipes = []
    started: set[int] = set()  # chapters a recipe already starts at
    for position, found in enumerate(answer.recipes):
        start = None
        if found.chapter is not None and found.chapter not in started:
            started.add(found.chapter)
            start = chapters[found.chapter].start_seconds
        recipes.append(
            Recipe(
                position=position,
                chapter_position=found.chapter,
                name=found.name,
                name_by="ai",
                name_confidence=found.confidence,
                start_seconds=start,
                start_by="ai",
            )
        )
    return recipes
